'''
Hola! 
I will do a lot of random note taking here. 

The idea is that I will have a place to run and test out different API's and other methods


Github SDK for alpaca-trade-api-python:
https://github.com/alpacahq/alpaca-trade-api-python
Reading this:
Can get historic data in Bars, Quotes, or Trades. 
2 ways to receive data:
- work with data as it's received with a generator (faster, need to process each item alone)
- wait for entire data, then work with dataframe.

Wow so I was really just looking at the deprecated version of the SDK. 
Here's the new Github SDK: 
https://github.com/alpacahq/alpaca-py#broker-api-new
Reading:
compared to the old one, this uses a more OOP approach. 
To submit a request, I will need to create a request object. 
For each method, there is some request model.



Okay I will need a good environment. And very good development principles. 
So whenever I pull in any dependencies, it needs to be a part of a virtualenv. 

The main reason is because I will need to set some environment variables in order to call the API. 

Paper trading API key: PK630S130BC6YEI9WGAN
Paper trading secret key: wOhUf6g2CuR6kDPZFCR7Wyiijh3Y77qpeet90yil


For reference:
os.getenv() is for getting
set using `os.environ['x'] = 'x'

'''

#from alpaca_trade_api.rest import REST, TimeFrame
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
import os
from math import floor
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

#API_KEY = os.getenv('API_KEY')
#SECRET_KEY = os.getenv('SECRET_KEY')
#api = REST()


# there are no keys required for crypto data 
client = CryptoHistoricalDataClient()
request = CryptoBarsRequest(
    symbol_or_symbols=["BTC/USD", "ETH/USD"],
    timeframe=TimeFrame.Day,
    start=datetime(2023, 4, 4)
)

bars = client.get_crypto_bars(request)

print(bars)
