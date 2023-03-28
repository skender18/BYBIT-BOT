import configparser
import datetime as dt
import json
import math
import os
import threading
import time

import pandas as pd
import pandas_ta as tap
import pybit
import pytz
import requests
import schedule
import ta
import telebot
from dotenv import load_dotenv
from pybit import HTTP, account_asset, spot
from scipy.stats import norm
from SkendLib import SuperTrend, black_scholes, round_down, send_email
from telebot import types

load_dotenv()


#SYMBOL
symbol = 'ETHUSDT'
coin = 'ETH'


#TELEGRAM
telegram_bot_key = os.getenv('TELEGRAM_BOT_API_KEY')
my_chat_id = os.getenv('MY_CHAT_ID')
group_chat_id = os.getenv('CHANNEL_CHAT_ID')
laura_chat_id = os.getenv('LAURA_CHAT_ID')
bot = telebot.TeleBot(telegram_bot_key)

# Security parameters
admin_id = 1865712919 # replace with the actual admin ID
user_file = 'users.json'

# load the user data from the json, if it exists
try:
    with open(user_file, 'r') as f:
        users = json.load(f)
except FileNotFoundError:
    # if the file does not exist, create the file and initialize the users dictionary
    with open(user_file, 'w') as f:
        users = {}
        json.dump(users, f)


#BYBIT
bybit_key = os.getenv('BYBIT_API_KEY')
bybit_secret = os.getenv('BYBIT_API_SECRET')

#Strategy Parameters
n1 = int(os.getenv('N1'))
n2 = int(os.getenv('N2'))
n3 = int(os.getenv('N3'))
n4 = int(os.getenv('N4'))
stop_loss = int(os.getenv('STOP_LOSS'))
take_profit = int(os.getenv('TAKE_PROFIT'))
st_atr_window = int(os.getenv('ST_ATR_WINDOW'))
st_atr_multiplier = int(os.getenv('ST_ATR_MULTIPLIER'))
upper_bound = int(os.getenv('UPPER_BOUND'))
lower_bound = int(os.getenv('LOWER_BOUND'))
rsi_window = int(os.getenv('RSI_WINDOW'))
url_bybit = 'https://api.bybit.com'

session_auth = spot.HTTP(
    endpoint=url_bybit,
    api_key=bybit_key, 
    api_secret=bybit_secret)

session_auth_account = account_asset.HTTP(
    endpoint=url_bybit,
    api_key=bybit_key,
    api_secret=bybit_secret)

session_unauth = spot.HTTP(endpoint=url_bybit)

        

def get_server_time():
    response = requests.get(url_bybit + "/v3/public/time")
    response = float(response.json()['result']['timeSecond'])
    response = pd.to_datetime(int(response), unit='s')
    time_zone = pytz.timezone("Europe/Amsterdam")
    response = response.tz_localize(pytz.utc).tz_convert(time_zone)
    return response.replace(tzinfo=None)


def get_kline():
    
    global kline_df
    
    url = "https://api.bybit.com/v2/public/kline/list"

    end_time = dt.datetime.now()
    start_time = end_time - dt.timedelta(hours=2000)
    interval = 60
    step = 200
    kline_data = []

    while start_time < end_time:
        startTime = str(int(start_time.timestamp()))
        end_time_step = start_time + dt.timedelta(hours=(step * interval / 60))
        endTime = str(int(end_time_step.timestamp()))
        req_params = {"symbol" : 'ETHUSD', 'interval' : interval, 'from' : startTime, 'to' : endTime}

        kline_chunk = json.loads(requests.get(url, params = req_params).text)['result']
        if len(kline_chunk) == 0:
            break

        kline_data.extend(kline_chunk)

        start_time = end_time_step

    kline_dict = {'open_time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': [], 'turnover': []}
    for kline in kline_data:
        kline_dict['open_time'].append(dt.datetime.fromtimestamp(kline['open_time']))
        kline_dict['open'].append(kline['open'])
        kline_dict['high'].append(kline['high'])
        kline_dict['low'].append(kline['low'])
        kline_dict['close'].append(kline['close'])
        kline_dict['volume'].append(kline['volume'])
        kline_dict['turnover'].append(kline['turnover'])

    kline_df = pd.DataFrame(kline_dict)
    kline_df.set_index('open_time', inplace=True)
    kline_df.iloc[:,0:6] = kline_df.iloc[:,0:6].astype(float)

    return kline_df


def add_signal():
    global prices_with_indicators
    
    try:
        #CHECK IF THE KLINE IS UPDATED
        if prices_with_indicators.index[-1].timestamp() > (get_server_time().timestamp() - dt.timedelta(minutes=60).total_seconds()):
            return prices_with_indicators
        
        else:
            prices_with_indicators = get_kline()
            super_trend = SuperTrend(prices_with_indicators['high'], prices_with_indicators['low'], prices_with_indicators['close'], st_atr_window, st_atr_multiplier)
            prices_with_indicators['STD'] = super_trend.super_trend_direction()
            prices_with_indicators['EMA_20'] = tap.ema(prices_with_indicators['close'], length=20)
            prices_with_indicators['EMA_50'] = tap.ema(prices_with_indicators['close'], length=50)
            prices_with_indicators['EMA_100'] = tap.ema(prices_with_indicators['close'], length=100)
            prices_with_indicators['EMA_200'] = tap.ema(prices_with_indicators['close'], length=200)
            prices_with_indicators['RSI'] = tap.rsi(prices_with_indicators['close'], length=rsi_window)
            prices_with_indicators['ssa'] = ta.trend.ichimoku_a(prices_with_indicators['high'], prices_with_indicators['low'])
            prices_with_indicators['ssb'] = ta.trend.ichimoku_b(prices_with_indicators['high'], prices_with_indicators['low'])

            return prices_with_indicators
    except:
        prices_with_indicators = get_kline()
        super_trend = SuperTrend(prices_with_indicators['high'], prices_with_indicators['low'], prices_with_indicators['close'], st_atr_window, st_atr_multiplier)
        prices_with_indicators['STD'] = super_trend.super_trend_direction()
        prices_with_indicators['EMA_20'] = tap.ema(prices_with_indicators['close'], length=20)
        prices_with_indicators['EMA_50'] = tap.ema(prices_with_indicators['close'], length=50)
        prices_with_indicators['EMA_100'] = tap.ema(prices_with_indicators['close'], length=100)
        prices_with_indicators['EMA_200'] = tap.ema(prices_with_indicators['close'], length=200)
        prices_with_indicators['RSI'] = tap.rsi(prices_with_indicators['close'], length=rsi_window)
        prices_with_indicators['ssa'] = ta.trend.ichimoku_a(prices_with_indicators['high'], prices_with_indicators['low'])
        prices_with_indicators['ssb'] = ta.trend.ichimoku_b(prices_with_indicators['high'], prices_with_indicators['low'])

        return prices_with_indicators
    
    
def check_signal():
    global prices_with_indicators
    global last_signal
    
    if 'last_signal' not in globals(): 
        last_signal = ''

    if 'prices_with_indicators' not in globals():
        add_signal()
    
    if (prices_with_indicators.index[-1].timestamp() > (get_server_time().timestamp() - dt.timedelta(minutes=60).total_seconds())
        and last_signal != ''):
        return last_signal

    else : 
        add_signal()
        
        if ((prices_with_indicators['RSI'].iloc[-1] < upper_bound)
            and (prices_with_indicators['EMA_50'].iloc[-1] > prices_with_indicators['EMA_100'].iloc[-1])
            and (prices_with_indicators['EMA_100'].iloc[-1] > prices_with_indicators['EMA_200'].iloc[-1])
            and (prices_with_indicators['ssa'].iloc[-1] > prices_with_indicators['ssb'].iloc[-1])
            and (prices_with_indicators['STD'].iloc[-1] == True)
            ):
            last_signal = 'BUY'

        elif ((prices_with_indicators['ssa'].iloc[-1] < prices_with_indicators['ssb'].iloc[-1])
            or (prices_with_indicators['EMA_100'].iloc[-1] < prices_with_indicators['EMA_200'].iloc[-1])
            or (prices_with_indicators['STD'].iloc[-1] == False)
            ):
            last_signal = 'SELL'
            
        else:
            last_signal = 'HOLD'
        
        return last_signal


def buy_spot(symbol):
    
    wallet = session_auth_account.query_asset_info()['result']['spot']
    for i in wallet['assets']:   
        if i['coin'] == 'USDT':
            qty_USDT = float(i['free'])
    
    session_auth.place_active_order(
        symbol=symbol,
        side="Buy", 
        type="MARKET",
        qty=qty_USDT #qty in btc!!!, min step is 0.001, so at lease abot 35 USDT must be on Your account
    )
    price = retrieve_last_price(symbol)
    quick_message = 'Buy order placed\nPrice: ' + str(price)
    print(quick_message)
    bot.send_message(chat_id=my_chat_id, text=quick_message)
    bot.send_message(chat_id=group_chat_id, text=quick_message)
    
 
def close_spot(symbol_USDT):            
    wallet = session_auth_account.query_asset_info()['result']['spot']
    for i in wallet['assets']:   
        if i['coin'] == 'ETH':
            qty_ETH = round_down(float(i['free']),4)
    
    session_auth.place_active_order(
        symbol=symbol_USDT,
        side="SELL",
        type="MARKET",
        qty=qty_ETH #BUY in USDT and SELL in ETH
    )
    price = retrieve_last_price(symbol)
    quick_message = 'Close order placed\nPrice: ' + str(price)
    print(quick_message)
    bot.send_message(chat_id=my_chat_id, text=quick_message)
    bot.send_message(chat_id=group_chat_id, text=quick_message)


def retrieve_wallet_balance(symbol=''):
    wallet = pd.DataFrame(session_auth.get_wallet_balance()['result']['balances'])
    wallet['total'] = wallet['total'].astype(float)
    try: 
        if symbol != '':
            wallet_filtered = wallet['coin'] == symbol
            wallet = wallet[wallet_filtered]
            return wallet
        else: 
            raise Exception('No symbol specified')
    except:
        print('Error in retrieve_wallet_balance') 


def retrieve_last_price(symbol):
    last_price = float(session_unauth.latest_information_for_symbol(symbol=symbol)['result']['lastPrice'])
    return last_price


def update_position():
    myobj = (dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    signal_detected = check_signal()
    message_sent = ('{}\nSignal detected : {}'.format(myobj,signal_detected))

 
    if (signal_detected == 'BUY'
        and retrieve_wallet_balance(coin)['total'].iloc[0] < 0.01
        ):
            
        buy_spot(symbol)
        return "BUY signal"


    if (signal_detected == 'SELL' 
        and retrieve_wallet_balance(coin)['total'].iloc[0] > 0.001):
        close_spot(symbol)
        return "SELL signal"
    
    try: 
        if (retrieve_last_price(symbol) > (float(session_auth.user_trade_records(symbol)['result'][0]['price'])*(1+take_profit/100))
        and retrieve_wallet_balance(coin)['total'].iloc[0] > 0.001
        or retrieve_last_price(symbol) < (float(session_auth.user_trade_records(symbol)['result'][0]['price'])*(1-stop_loss/100))
        and retrieve_wallet_balance(coin)['total'].iloc[0] > 0.001
        ):
            close_spot(symbol)
            return "tp/sl"
            
        else:
            pass

    except:
        pass
    
    print('Signal detected : {} ({})'.format(signal_detected,myobj))
    
def signal_df():
   global df_signal
   try:
       signal= check_signal()
       now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
       df_signal = df_signal.append(pd.DataFrame([signal], columns=['Signal'], index=[now]))
       
   except NameError:
       signal = check_signal()
       now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
       df_signal = pd.DataFrame([signal], columns=['Signal'], index=[now])
   if len(df_signal) > 1:
       if df_signal.iloc[-1]["Signal"] != df_signal.iloc[-2]["Signal"]:
            message = "The last signal is different from the signal before. {} signal detected at {}".format(df_signal.iloc[-1]["Signal"], (dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S"))
            bot.send_message(chat_id=my_chat_id, text=message)
            bot.send_message(chat_id=group_chat_id, text=message)
       else :
           pass


def check_awake():
    answer = "I'm awake\nLast price for {}: {}\nLast signal: {}\nLast update: {}".format(symbol, retrieve_last_price(symbol), check_signal(), (dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S"))
    return answer


@bot.message_handler(commands=['newuser'])
def new_user(message):
    # get the user ID and chat ID from the message object
    user_id = message.from_user.id
    chat_id = message.chat.id
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    user_name = message.from_user.username
    
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    
    if (str(user_id) in user_data and user_data[str(user_id)]['access_granted'] == True):
        bot.send_message(chat_id=chat_id, text="You already have access to the bot.")
        
    elif (str(user_id) in user_data and user_data[str(user_id)]['access_granted'] == False):
        bot.send_message(chat_id=chat_id, text="Your access to the bot has been refused. Contact the admin for more information. @skenderou")
        bot.send_message(chat_id=admin_id, text="User {} ({} {}) has requested access to the bot but it has been refused.".format(user_id, first_name, last_name))
        
    
    else :
        callback_data = '{}:{}:{}:{}:{}'.format(user_id, chat_id, first_name, last_name, user_name)

        # create a message with user information
        message_text = "New user: \nUser ID: {}\nChat ID: {}\nFirst name: {}\nLast name: {}\nUsername: {}".format(user_id, chat_id, message.from_user.first_name, message.from_user.last_name, message.from_user.username)

        # create a keyboard with "Give access" and "Refuse access" buttons
        keyboard = types.InlineKeyboardMarkup()
        access_button = types.InlineKeyboardButton(text='Give access', callback_data='give_access_{}'.format(callback_data))
        refuse_button = types.InlineKeyboardButton(text='Refuse access', callback_data='refuse_access_{}'.format(callback_data))
        keyboard.add(access_button, refuse_button)

        # send the message to the admin
        bot.send_message(chat_id=admin_id, text=message_text, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: 'give_access' in call.data or 'refuse_access' in call.data)
def access_callback(call):
    callback_data = call.data.split('_')[2]
    user_id, chat_id, first_name, last_name, user_name = callback_data.split(':')
    
    # check which button was pressed
    if 'give_access' in call.data:
        # load the existing user data from the file
        with open(user_file, 'r') as f:
            user_data = json.load(f)
            
        # add the user data to the user_data dictionary
        user_data[user_id] = {
            'user_id': user_id,
            'chat_id': chat_id,
            'first_name': first_name,
            'last_name': last_name,
            'username': user_name,
            'access_granted': True
        }

        # write the user data to the file
        with open(user_file, 'w') as f:
            json.dump(user_data, f)

        # send a message to the user to inform them that they have been given access
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(chat_id=chat_id, text="You have been given access to the bot. Hello {}!".format(first_name))
        bot.send_message(chat_id=admin_id, text="Access has been given to user {}.".format(user_id))

    else:
        if 'refuse_access' in call.data:
            # load the existing user data from the file
            with open(user_file, 'r') as f:
                user_data = json.load(f)
                
            # add the user data to the user_data dictionary
            user_data[user_id] = {
                'user_id': user_id,
                'chat_id': chat_id,
                'first_name': first_name,
                'last_name': last_name,
                'username': user_name,
                'access_granted': False
            }

            # write the user data to the file
            with open(user_file, 'w') as f:
                json.dump(user_data, f)
            
            # send a message to the user to inform them that their access has been refused
            bot.send_message(chat_id=chat_id, text="Your access has been refused. Please contact the bot admin.")
            bot.send_message(chat_id=admin_id, text="Access has been refused to user {}.".format(user_id))


@bot.message_handler(commands=['access'])
def access_modification(message):
    if message.from_user.id == admin_id:
        keyboard_access_modification = types.InlineKeyboardMarkup()
        access_add_button = types.InlineKeyboardButton(text='Add access', callback_data='add_access')
        access_remove_button = types.InlineKeyboardButton(text='Remove access', callback_data='remove_access')
        keyboard_access_modification.add(access_add_button, access_remove_button)
        bot.send_message(chat_id=admin_id, text='What action would you like to do ?', reply_markup=keyboard_access_modification)
    
    else:
        bot.send_message(chat_id=message.chat.id, text="You don't have access to this command.")
        bot.send_message(chat_id=admin_id, text="User {}  ({} {})tried to access the access modification command.".format(message.from_user.id, message.from_user.first_name, message.from_user.last_name))
    
@bot.callback_query_handler(func=lambda call: 'add_access' in call.data or 'remove_access' in call.data)
def access_modification_callback(call):

    if 'add_access' in call.data:
        #ask for user ID
        bot.send_message(chat_id=admin_id, text="Please enter the user ID of the user you want to give access to.")
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.register_next_step_handler(call.message, add_access)
    elif 'remove_access' in call.data:
        #ask for user ID
        bot.send_message(chat_id=admin_id, text="Please enter the user ID of the user you want to remove access from.")
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.register_next_step_handler(call.message, remove_access)

def add_access(message):
    user_id = message.text
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if (str(user_id) in user_data and user_data[str(user_id)]['access_granted'] == True):
        # send a message to the user to inform them that they already have access
        bot.send_message(chat_id=admin_id, text="This user already has access to the bot.")
    elif (str(user_id) in user_data and user_data[str(user_id)]['access_granted'] == False):
        user_data[str(user_id)]['access_granted'] = True
        with open(user_file, 'w') as f:
            json.dump(user_data, f)
        bot.send_message(chat_id=admin_id, text="Access has been given to user {} ({}).".format(user_id, user_data[str(user_id)]['first_name'] + ' ' + user_data[str(user_id)]['last_name']))
        bot.send_message(chat_id=user_data[str(user_id)]['chat_id'], text="You have been given access to the bot. Hello {}!".format(user_data[str(user_id)]['first_name']))
        
    else :
        bot.send_message(chat_id=admin_id, text="This user does not exist.")

def remove_access(message):
    user_id = message.text
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if (str(user_id) in user_data and user_data[str(user_id)]['access_granted'] == True):
        user_data[str(user_id)]['access_granted'] = False
        with open(user_file, 'w') as f:
            json.dump(user_data, f)
        bot.send_message(chat_id=admin_id, text="Access has been removed from user {} ({}).".format(user_id, user_data[str(user_id)]['first_name'] + ' ' + user_data[str(user_id)]['last_name']))
    elif (str(user_id) in user_data and user_data[str(user_id)]['access_granted'] == False):
        # send a message to the user to inform them that they already have access
        bot.send_message(chat_id=admin_id, text="This user already has no access to the bot.")
        bot.send_message(chat_id=user_data[str(user_id)]['chat_id'], text="Your access to the bot has been removed. Ask the bot admin to give you access again.")
    else :
        bot.send_message(chat_id=admin_id, text="This user does not exist.")


@bot.message_handler(commands=['ta'])
def ta_command(message):
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if (str(message.from_user.id) in user_data and user_data[str(message.from_user.id)]['access_granted'] == True):

        signal = check_signal()
        df = prices_with_indicators
        answer = "Last candle: {}\n".format(df.index[-1])
        answer += "Signal: {}\n".format(signal)
        answer += "RSI: {:.2f}\n".format(df.loc[df.index[-1], "RSI"])
        answer += "EMA 20: {:.2f}\n".format(df.loc[df.index[-1], "EMA_20"])
        answer += "EMA 50: {:.2f}\n".format(df.loc[df.index[-1], "EMA_50"])
        answer += "EMA 100: {:.2f}\n".format(df.loc[df.index[-1], "EMA_100"])
        answer += "EMA 200: {:.2f}\n".format(df.loc[df.index[-1], "EMA_200"])
        answer += "Ichimoku A: {:.2f}\n".format(df.loc[df.index[-1], "ssa"])
        answer += "Ichimoku B: {:.2f}\n".format(df.loc[df.index[-1], "ssb"])
        answer += "SuperTrend: {}\n".format(df.loc[df.index[-1], "STD"])
        bot.send_message(chat_id=message.chat.id, text=answer)
    else:
        bot.send_message(chat_id=message.chat.id, text="You do not have access to this command. Please ask the bot admin to give you access.")
    
@bot.message_handler(commands=['awake'])
def awake_command(message):
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if (str(message.from_user.id) in user_data and user_data[str(message.from_user.id)]['access_granted'] == True):
        answer = check_awake()
        bot.send_message(chat_id=message.chat.id, text=answer)
        
    else:
        bot.send_message(chat_id=message.chat.id, text="You do not have access to this command. Please ask the bot admin to give you access.")
    

@bot.message_handler(commands=['news'])
def news_command(message):
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if (str(message.from_user.id) in user_data and user_data[str(message.from_user.id)]['access_granted'] == True):
        api_key = os.getenv('NEWS_KEY')
        url = f'https://newsapi.org/v2/everything?q=crypto&sortBy=publishedAt&apiKey={api_key}'
        response = requests.get(url)
        news_data = response.json()

        for i in range(2):
            title = news_data['articles'][i]['title']
            url = news_data['articles'][i]['url']
            bot.send_message(message.chat.id, f'{i+1}. {title}\n{url}')
    else:
        bot.send_message(chat_id=message.chat.id, text="You do not have access to this command. Please ask the bot admin to give you access.")


@bot.message_handler(commands=['price'])
def price_command(message):
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if (str(message.from_user.id) in user_data and user_data[str(message.from_user.id)]['access_granted'] == True):
        top_symbols = ['BTC', 'ETH', 'XRP', 'LTC', 'BCH', 'BNB']
        buttons = types.InlineKeyboardMarkup()
        for symbol in top_symbols:
            button = types.InlineKeyboardButton(symbol, callback_data=f"price_{symbol}")
            buttons.add(button)
        bot.send_message(message.chat.id, "Please select a symbol:", reply_markup=buttons)
    else:
        bot.send_message(chat_id=message.chat.id, text="You do not have access to this command. Please ask the bot admin to give you access.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("price_"))
def handle_callback_price(call):
    symbol = call.data.split("_")[1]
    url = f'https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}USDT'
    response = requests.get(url)
    last_price = response.json()

    if last_price is None:
        bot.answer_callback_query(call.id, text=f"Invalid Symbol:{symbol}")
        return

    price = float(last_price['lastPrice'])
    high = float(last_price['highPrice'])
    low = float(last_price['lowPrice'])
    price_symbol = "Last price of {}/USDT : {:,.2f}  \nHigh : {:,.2f} \nLow : {:,.2f}".format(symbol,price,high,low)
    bot.edit_message_text(price_symbol, chat_id=call.message.chat.id, message_id=call.message.message_id)


@bot.message_handler(commands=['wallet'])
def wallet_info(message):
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if message.from_user.id == admin_id:
        top_coins = ['BTC', 'ETH', 'USDT', 'USDC', 'BUSD']
        buttons = types.InlineKeyboardMarkup()
        for coins in top_coins:
            button = types.InlineKeyboardButton(coins, callback_data=f"wallet_{coins}")
            buttons.add(button)
        bot.send_message(message.chat.id, "Please select a coin:", reply_markup=buttons)
    else:
        bot.send_message(message.chat.id, "You are not allowed to use this command")
        bot.send_message(my_chat_id,"Unauthorized access to /wallet command from {} ({})".format(message.from_user.id, user_data[str(message.from_user.id)]['first_name'] + ' ' + user_data[str(message.from_user.id)]['last_name']))


@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet_'))
def handle_callback_wallet(call):
    coins = call.data.split("_")[1]
    balance = session_auth.get_wallet_balance()['result']['balances']
    for coin_balance in balance:
        if coin_balance['coin'] == coins:
            total_coin = coin_balance['total']
            answer = "Coin: {} / Amount: {:.3f}".format(coins, float(total_coin))
            break
    else:
        answer = "Invalid coin"
    bot.edit_message_text(answer, chat_id=call.message.chat.id, message_id=call.message.message_id)
  

@bot.message_handler(commands=['black_scholes'])
def handle_black_scholes(message):
    with open(user_file, 'r') as f:
        user_data = json.load(f)
        
    if (str(message.from_user.id) in user_data and user_data[str(message.from_user.id)]['access_granted'] == True):
        try:
            args = message.text.split()[1:]
            option_type = args[0]
            S = float(args[1])
            K = float(args[2])
            T = float(args[3])
            r = float(args[4])
            sigma = float(args[5])
            result = black_scholes(option_type, S, K, T, r, sigma)
            bot.send_message(message.chat.id, result)
            
        except (IndexError, ValueError):
            bot.send_message(message.chat.id, 'Usage: /black_scholes <option_type> <S> <K> <T> <r> <sigma>\n Example: /black_scholes call 100 100 1 0.05 0.2')
    else:
        bot.send_message(chat_id=message.chat.id, text="You do not have access to this command. Please ask the bot admin to give you access.")


@bot.message_handler(commands=['start']) 
def send_welcome(message):
    answer = "Hello{}, welcome to my bot! \nThis bot is developped for fun, the information provided by this bot are not financial advice. \nUse /help to see the list of commands available. \n\nTo check if you have access to the bot, please use /newuser command. \n\nIf you need help, please contact @skenderou".format(message.from_user.first_name)
    bot.reply_to(message, answer)
    


@bot.message_handler(commands=['bot_updated']) 
def bot_updated_command(message):
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if message.from_user.id == admin_id:
        bot.send_message(group_chat_id, "Hi, I'm updated !")
    else: 
        pass
    
    
@bot.message_handler(commands=['bot_alive']) 
def bot_alive_command(message):
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if message.from_user.id == admin_id:
        bot.send_message(group_chat_id, "Hi, I'm alive !")
    else: 
        pass

@bot.message_handler(commands=['email'])
def send_email_telegram(message):    
    if message.from_user.id == admin_id:
        try:
            send_email(message.text.split()[1], message.text.split()[2], message.text.split()[3])
            bot.reply_to(message, "Email sent to {}".format(message.text.split()[1]))
            print("Email sent to {}".format(message.text.split()[1]))
        except:
            bot.reply_to(message, "Error while sending email to {}".format(message.text.split()[1]))
            bot.send_message(message.from_user.id, "The format of the command is /email [email] [company_name] [langage (fr/en)]]")
            print("Error while sending email to {}".format(message.text.split()[1]))

@bot.message_handler(commands=['help'])
def help_command(message):
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    if (str(message.from_user.id) in user_data and user_data[str(message.from_user.id)]['access_granted'] == True):
        bot.send_message(message.chat.id, '''
        Available commands:
        /news - Returns the latest 2 news articles about crypto
        /price - Returns the last, high and low price of the selected symbol in USDT
        /ta - Returns technical analysis of the traded symbol
        /awake - Check if the bot is awake, return the last signal/price/position
        /newuser - Check if you have access to the bot
        /blackscholes - Returns the price of a call or put option
        
        some other commands are available, try to find them
        ''')
    else:bot.send_message(message.chat.id, '''
        first you need to register to the bot, please use /newuser command.
        ''')
    
@bot.message_handler(commands=['help_admin'])
def help_command(message):
    if message.from_user.id == admin_id:
        bot.send_message(message.chat.id, '''
        Available commands:
        /access - Give access to the bot to a new user
        /bot_updated - Send a message to the group chat to inform that the bot is updated
        /bot_alive - Send a message to the group chat to inform that the bot is alive
        /email - Send an cover letter to a me         
        ''')
    else:
        bot.send_message(message.chat.id, "You are not allowed to use this command")
        bot.send_message(admin_id, "Unauthorized access to /help_admin command from " + str(message.from_user.id) + " " + str(message.from_user.first_name) + " " + str(message.from_user.last_name) + " " + str(message.from_user.username) + " " + str(message.from_user.language_code))

#############################################################################################################    
    

#Initialize the bot for the NOHUP
check_signal()
update_position()
bot.send_message(my_chat_id,"I'm online !")

schedule.every().hour.at(":01").do(check_signal)
schedule.every().hour.at(":02").do(update_position)
schedule.every(30).minutes.do(check_awake)


def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    schedule_thread = threading.Thread(target=run_schedule)
    schedule_thread.start()
    bot.polling()