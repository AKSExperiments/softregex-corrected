#!/usr/bin/env python
# coding: utf-8

# # Evaluation

# In[14]:


import os
import argparse
import logging

import torch
from torch.optim.lr_scheduler import StepLR, ReduceLROnPlateau
import torchtext

import seq2seq

from seq2seq.trainer import SupervisedTrainer, SelfCriticalTrainer
from seq2seq.models import EncoderRNN, DecoderRNN, Seq2seq, TopKDecoder
from seq2seq.loss import Perplexity, NLLLoss, PositiveLoss
from seq2seq.optim import Optimizer
from seq2seq.dataset import SourceField, TargetField
from seq2seq.evaluator import Predictor, Evaluator
from seq2seq.util.checkpoint import Checkpoint
import torch.nn.functional as F

import subprocess
import sys

import websockets
import asyncio

import warnings
warnings.filterwarnings('ignore')

try:
    raw_input          # Python 2
except NameError:
    raw_input = input  # Python 3
    
# Prepare dataset
src = SourceField()
tgt = TargetField()

# data/kb/train/data.txt
#data/NL-RX-Synth/train/data.txt
#data/NL-RX-Turk/train/data.txt


dataset = 'kb13'

if len(sys.argv) < 1:
    sys.exit(-1)

dataset = sys.argv[1]

datasets = {
    'kb13': ('KB13', 30, 60),
    'NL-RX-Synth': ('NL-RX-Synth', 10, 40),
    'NL-RX-Turk': ('NL-RX-Turk', 10, 40),
    'custom': ('NL-RX-SYNTH', 30, 100)
}


data_tuple = datasets[dataset]

# max_len = 60
max_len = data_tuple[2]
def len_filter(example):
    return len(example.src) <= max_len
train = torchtext.data.TabularDataset(
    path='data/' + data_tuple[0] + '/train/data.txt', format='tsv',
    fields=[('src', src), ('tgt', tgt)],
    filter_pred=len_filter
)
dev = torchtext.data.TabularDataset(
    path='data/' + data_tuple[0] + '/val/data.txt', format='tsv',
    fields=[('src', src), ('tgt', tgt)],
    filter_pred=len_filter
)
test = torchtext.data.TabularDataset(
    path='data/' + data_tuple[0] + '/test/data.txt', format='tsv',
    fields=[('src', src), ('tgt', tgt)],
    filter_pred=len_filter
)

src.build_vocab(train, max_size=500)
tgt.build_vocab(train, max_size=500)
input_vocab = src.vocab
output_vocab = tgt.vocab

# Prepare loss
weight = torch.ones(len(tgt.vocab))
pad = tgt.vocab.stoi[tgt.pad_token]

loss = NLLLoss(weight, pad)

if torch.cuda.is_available():
    loss.cuda()
    
seq2seq_model = None
optimizer = None


# In[15]:


def decode_tensor(tensor, vocab):
    tensor = tensor.view(-1)
    words = []
    for i in tensor:
        word = vocab.itos[i.cpu().numpy()]
        if word == '<eos>':
            return ' '.join(words) 
        if word != '<sos>' and word != '<pad>' and word != '<eos>':
            words.append(word)
        #if word != '<sos>':
        #    words.append(word)
        #print('|' + word + '|')
    return ' '.join(words)


# In[16]:


from regexDFAEquals import regex_equiv_from_raw, unprocess_regex, regex_equiv


# In[17]:


batch_size = 1


# In[18]:


hidden_size = 256
word_embedding_size = 128

bidirectional = True

encoder = EncoderRNN(len(src.vocab), max_len, hidden_size, dropout_p=0.1,rnn_cell='lstm',
                     bidirectional=bidirectional, n_layers=2, variable_lengths=True)
decoder = DecoderRNN(len(tgt.vocab), max_len, hidden_size * 2 if bidirectional else hidden_size,rnn_cell='lstm',
                     dropout_p=0.25, use_attention=True, bidirectional=bidirectional, n_layers=2,
                     eos_id=tgt.eos_id, sos_id=tgt.sos_id)

seq2seq_model = Seq2seq(encoder, decoder)
if torch.cuda.is_available():
    seq2seq_model.cuda()

for param in seq2seq_model.parameters():
    param.data.uniform_(-0.1, 0.1)


optimizer = Optimizer(torch.optim.Adam(seq2seq_model.parameters()),  max_grad_norm=5)


t = SupervisedTrainer(loss=loss, batch_size=8,
                      checkpoint_every=100,
                      print_every=10000, expt_dir='./lstm_model/'+data_tuple[0]+'/Deepregex')

seq2seq_model = torch.nn.DataParallel(seq2seq_model)

seq2seq_model = t.train(seq2seq_model, train,
                  num_epochs=1, dev_data=dev,
                  optimizer=optimizer,
                  teacher_forcing_ratio=0.5,
                  resume=True)

optimizer_new = Optimizer(torch.optim.Adadelta(seq2seq_model.parameters(), lr=0.05))


sc_t = SelfCriticalTrainer(loss=PositiveLoss(mode='prob', prob_model=None, loss_vocab=None), batch_size=32,
                           checkpoint_every=200000, print_every=100, expt_dir='./lstm_model/'+data_tuple[0]+'/SoftRegex', output_vocab=output_vocab)



seq2seq_model = sc_t.train(seq2seq_model, train,
                  num_epochs=1, dev_data=dev,
                  optimizer=optimizer_new, teacher_forcing_ratio=0.5,
                  resume=True)


data = test


# In[19]:


seq2seq_model.eval()

loss.reset()
match = 0
total = 0

device = None if torch.cuda.is_available() else -1
batch_iterator = torchtext.data.BucketIterator(
    dataset=data, batch_size=batch_size,
    sort=False, sort_key=lambda x: len(x.src),
    device=device, train=False)



# In[20]:


def refine_outout(regex):
    par_list = []
    word_list = regex.split()
    
    for idx, word in enumerate(word_list):
        if word == '(' or word == '[' or word == '{':
            par_list.append(word)

        if word == ')' or word == ']' or word == '}':
            if len(par_list) == 0:
                word_list[idx] = ''
                continue

            par_in_list = par_list.pop()
            if par_in_list == '(':
                word_list[idx] = ')'
            elif par_in_list == '[':
                word_list[idx] = ']'
            elif par_in_list == '{':
                word_list[idx] = '}'
            
    while len(par_list) != 0:
        par_in_list = par_list.pop()
        if par_in_list == '(':
            word_list.append(')')
        elif par_in_list == '[':
            word_list.append(']')
        elif par_in_list == '{':
            word_list.append('}')
            
    word_list = [word for word in word_list if word != '']
    
    return ' '.join(word_list)


# In[22]:


predictor = Predictor(seq2seq_model, input_vocab, output_vocab)


async def listen():
    url = "ws://showmeregex.centralus.cloudapp.azure.com:8080"
    async with websockets.connect(url) as ws:
        await ws.send("type:model")
        while True:
            input_string = await ws.recv()
            input_str_arr = input_string.split(":", 1)
            client = input_str_arr[0]
            input_string = input_str_arr[1]
            generated_string = ' '.join([x for x in predictor.predict(input_string.strip().split())[:-1] if x != '<pad>'])
            generated_string = refine_outout(generated_string)
            print("Input string: ", input_string)
            print("Predicted: ", generated_string)
            await ws.send(client + ":" + generated_string)


asyncio.get_event_loop().run_until_complete(listen())




