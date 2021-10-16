from flask import Flask
from flask_restful import reqparse, Api, Resource

app = Flask(__name__)
api = Api(app)

parser = reqparse.RequestParser()
parser.add_argument('query')


class RegexGenerator(Resource):
    def get(self):
        args = parser.parse_args()
        user_query = args['query']
        print("Hello World")

        return "Very Smart Regex"


api.add_resource(RegexGenerator, '/')

if __name__ == '__main__':
    app.run(debug=True)
