#import alpaca_trade_api as tradeapi
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, CryptoTradesRequest
from alpaca.trading.requests import GetOrdersRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import logging  
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

# ENABLE LOGGING
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load Environment Variables
API_KEY = os.getenv('APCA_API_KEY_ID')
SECRET_KEY = os.getenv('APCA_API_SECRET_KEY')

# Alpaca Trading Client
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)


# Alpaca Market Data Client
data_client = CryptoHistoricalDataClient()

# Trading variables
trading_pair = 'BTC/USD'
notional_size = 20000
spread = 0.00
total_fees = 0
buying_price, selling_price = 0.00, 0.00
buy_order_price, sell_order_price = 0.00, 0.00

buy_order, sell_order = None, None
current_price = 0.00
client_order_str = 'scalping'

# Wait time in between each bar request
waitTime = 60

# Time range for the latest bar data
diff = 5

# Current position of the trading pair on Alpaca
current_position = 0.00

# Threshold percentage to cut losses (0.5%)
cut_loss_threshold = 0.005

# Alpaca trading fee is 0.3% (tier based)
trading_fee = 0.003




async def main():
    '''
    Main function to get latest asset data and check possible trade conditions
    '''

    # closes all positions AND cancel all open orders
    trading_client.close_all_positions(cancel_orders=True)
    logger.info("Closed all positions")

    while True:
        logger.info('------------------------------------------------')
        l1 = loop.create_task(get_crypto_bar_data(trading_pair))

        # Wait for tasks to finish 
        await asyncio.wait([l1])
        print("Done, going to check condition")
        # Check if any trading condition is met
        await check_condition()

        # Wait for a certain amount of time in between each bar request
        await asyncio.sleep(60)

        print('i am here')


async def get_crypto_bar_data(trading_pair):
    ''' 
    Get Crypto bar data from Alpaca for the last diff minutes
    '''
    time_diff = datetime.utcnow() - relativedelta(minutes=diff)
    logger.info("Getting crypto bar data for {0} from {1}".format(trading_pair, time_diff))

    # Defining Bar data request parameters
    request_params = CryptoBarsRequest(
        symbol_or_symbols=[trading_pair],
        timeframe=TimeFrame.Minute,
        start=time_diff
    )

    # Get Bar Data from alpaca
    bars_df = data_client.get_crypto_bars(request_params).df
    # Calculate the order prices 
    global buying_price, selling_price, current_position
    buying_price, selling_price = calc_order_price(bars_df)
    bars_df.to_csv('a.csv')

    if len(get_positions()) > 0:
        current_position = float(json.loads(get_positions()[0].json())['qty'])

        buy_order = False
    else:
        sell_order = False

    return bars_df

async def check_condition():
    '''
    Check the market conditions to see what limit orders to place 
    Strategy: 
    - Only consider placing orders if the spread is greater than the total fees after fees are taking into account
    - If the spread is greater than the total fees and we DO NOT have a position, then place a BUY order 
    - If the spread is greater than the total fees and we DO have a position, then place a SELL order 
    
    - If we DO NOT have a position, 
        a BUY order is in place and 
        The current price is more than the price we would have sold at, 
    - Then close the buy limit order. 

    - If we DO have a position,
        a sell order is in place and
        the current price is less than the price we would have sold at, 
    - Then close the sell limit order. 
    ''' 
    
    global buy_order, sell_order, current_position, current_price, buying_price, selling_price, spread, total_fees, buy_order_price, sell_order_price
    get_open_orders()
    logger.info("Current position is: {0}".format(current_position))
    logger.info("Buy order status: {0}".format(buy_order))
    logger.info("Sell order status: {0}".format(sell_order))
    logger.info("Buy_order_price: {0}".format(buy_order_price))
    logger.info("Sell_order_price: {0}".format(sell_order_price))

    # If the spread is less than the fees, do not place an order 
    if spread < total_fees:
        logger.info("Spread is less than total fees, Not a profitable opportunity to trade")
    else:
        # If we do not have a position, there are no open orders, and spread is greater than total fees, place limit buy order at the buying price 
        if current_position <= 0.01 and (not buy_order) and current_price > buying_price:
            buy_limit_order = await post_alpaca_order(buying_price, selling_price, 'buy')
            sell_order = False
            if buy_limit_order:
                logger.info("Placed buy limit order at {0}".format(buying_price))

        # If we have a position, no open orders and the spread that can be captured is greater than fees, place a limit sell order at the sell_order_price
        if current_position >= 0.01 and (not sell_order) and current_price < sell_order_price:
            sell_limit_order = await post_alpaca_order(buying_price, selling_price, 'sell')
            buy_order = False 
            if sell_limit_order:
                logger.info("Placed sell limit order at {0}".format(selling_price))

        # Cutting losses 
        # If we do not have a position, an open buy order and the current price is above the selling price, cancel the buy limit order
        logger.info("Threshold price to cancel any buy limit order: {0}".format(sell_order_price * (1 + cut_loss_threshold)))
        if current_position <= 0.01 and buy_order and current_price > (sell_order_price * (1 + cut_loss_threshold)):
            trading_client.cancel_orders()
            buy_order = False
            logger.info("Current price > Selling price. Closing buy limit order, will place again in next check")

        # If we do have a position and an open sell order and current price is below buying price, cancel sell limit order 
        logger.info("Threshold price to cancel any sell limit order: {0}".format(buy_order_price * (1 - cut_loss_threshold)))
        if current_position >= 0.01 and sell_order and current_price < (buy_order_price * (1 - cut_loss_threshold)):
            trading_client.cancel_orders()
            sell_order = False
            logger.info("Current price < buying price. Closing sell limit order, will place again in next check")
    print("condition checked")

    return 

def calc_order_price(bars_df):
    
    global spread, total_fees, current_price
    max_high = bars_df['high'].max()
    min_low = bars_df['low'].min()
    mean_vwap = bars_df['vwap'].mean()
    current_price = bars_df['close'].iloc[-1]

    logger.info("Closing price: {0}".format(current_price))
    logger.info("Mean VWAP: {0}".format(mean_vwap))
    logger.info("Min Low: {0}".format(min_low))
    logger.info("Max High: {0}".format(max_high))

    # Buying price is 0.2% above the min low 
    buying_price = round(min_low*1.002, 2)
    # Selling price is 0.2% below the max high
    selling_price = round(max_high*0.998, 1)

    buying_fee = trading_fee * buying_price
    selling_fee = trading_fee * selling_price
    total_fees = round(buying_fee + selling_fee, 2)

    logger.info("Buying price: {0}".format(buying_price))
    logger.info("Selling price: {0}".format(selling_price))
    logger.info("Total fees: {0}".format(total_fees))

    # Calculate the spread 
    spread = round(selling_price - buying_price, 2)

    logger.info(
        "Spread that can be captured: {0}".format(spread)
    )

    return buying_price, selling_price

def get_positions():
    positions = trading_client.get_all_positions()
    return positions
    

def get_open_orders():
    orders = trading_client.get_orders()
    num_orders = len(orders)
    logger.info("Number of open orders: {0}".format(num_orders))

    global buy_order, sell_order

    for i in range(len(orders)):
        ord = json.loads(orders[i].json())
        logger.info("Order type: {0} Order side: {1} Order notional: {2} Order Symbol: {3} Order Price: {4}".format(
            ord['type'], ord['side'], ord['notional'], ord['symbol'], ord['limit_price']
        ))
        if ord['side'] == 'buy':
            buy_order = True
        if ord['side'] == 'sell':
            sell_order = True

    return num_orders

async def post_alpaca_order(buy_price, sell_price, side):
    '''
    Post an order to Alpaca
    '''
    global buy_order_price, sell_order_price, buy_order, sell_order
    try:
        if side == 'buy':
            logger.info("Buying at: {0}".format(price))
            limit_order_data = LimitOrderRequest(
                symbol="BTCUSD",
                limit_price=buy_price,
                notional=notional_size,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC,
                client_order_id=client_order_str)
            buy_limit_order = trading_client.submit_order(
                order_data=limit_order_data
            )
            buy_order_price = buy_price
            sell_order_price = sell_price

            logger.info("Buy Limit Order placed for BTC/USD at: {0}".format(buy_limit_order.limit_price))
            return buy_limit_order

        else:
            limit_order_data = LimitOrderRequest(
                symbol="BTCUSD",
                limit_price=sell_price,
                notional=notional_size,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
                client_order_id=client_order_str
            )
            sell_limit_order = trading_client.submit_order(
                order_data=limit_order_data
            )
            sell_order_price = sell_price
            buy_order_price = buy_price

            logger.info("Sell Limit Order placed for BTC/USD at: {0}".format(sell_limit_order.limit_price))
            return sell_limit_order

    except Exception as e:
        logger.exception(
            "There was an issue posting order to Alpaca: {0}".format(e))
        return False


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.close()