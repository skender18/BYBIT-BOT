import os
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import math
from scipy.stats import norm
import smtplib
from email.mime.text import MIMEText

load_dotenv()

# Supertrend
'''
Créé par le trader français Olivier Seban, 
le Supertrend est un indicateur technique qui vise à détecter les tendances des cours. 
C'est un outil assez utilisé par les analystes et notamment en ce qui concerne 
son utilité pour fixer des "stops" de protection.

Ce n'est cependant pas sa seule qualité 
et nous verrons plus bas qu'il est assez performant pour faire du suivi de tendance 
tout en filtrant efficacement les petits mouvements de cours 
qui représentent des corrections intermédiaires mais sans menacer la tendance de fond. 
On pourra ainsi se laisser porter par une longue tendance directive, 
génératrice des plus gros gains

https://www.abcbourse.com/apprendre/11_le_supertrend.html
'''
# Classe de définition
class SuperTrend():
    def __init__(
        self,
        high,
        low,
        close,
        atr_window=10,
        atr_multi=3
    ):
        self.high = high
        self.low = low
        self.close = close
        self.atr_window = atr_window
        self.atr_multi = atr_multi
        self._run()
        
    def _run(self):
        # calculate ATR
        price_diffs = [self.high - self.low, 
                    self.high - self.close.shift(), 
                    self.close.shift() - self.low]
        true_range = pd.concat(price_diffs, axis=1)
        true_range = true_range.abs().max(axis=1)
        # default ATR calculation in supertrend indicator
        atr = true_range.ewm(alpha=1/self.atr_window,min_periods=self.atr_window).mean() 
        # atr = ta.volatility.average_true_range(high, low, close, atr_period)
        # df['atr'] = df['tr'].rolling(atr_period).mean()
        
        # HL2 is simply the average of high and low prices
        hl2 = (self.high + self.low) / 2
        # upperband and lowerband calculation
        # notice that final bands are set to be equal to the respective bands
        final_upperband = upperband = hl2 + (self.atr_multi * atr)
        final_lowerband = lowerband = hl2 - (self.atr_multi * atr)
        
        # initialize Supertrend column to True
        supertrend = [True] * len(self.close)
        
        for i in range(1, len(self.close)):
            curr, prev = i, i-1
            
            # if current close price crosses above upperband
            if self.close[curr] > final_upperband[prev]:
                supertrend[curr] = True
            # if current close price crosses below lowerband
            elif self.close[curr] < final_lowerband[prev]:
                supertrend[curr] = False
            # else, the trend continues
            else:
                supertrend[curr] = supertrend[prev]
                
                # adjustment to the final bands
                if supertrend[curr] == True and final_lowerband[curr] < final_lowerband[prev]:
                    final_lowerband[curr] = final_lowerband[prev]
                if supertrend[curr] == False and final_upperband[curr] > final_upperband[prev]:
                    final_upperband[curr] = final_upperband[prev]

            # to remove bands according to the trend direction
            if supertrend[curr] == True:
                final_upperband[curr] = np.nan
            else:
                final_lowerband[curr] = np.nan
                
        self.st = pd.DataFrame({
            'Supertrend': supertrend,
            'Final Lowerband': final_lowerband,
            'Final Upperband': final_upperband
        })
        
    def super_trend_upper(self):
        return self.st['Final Upperband']
        
    def super_trend_lower(self):
        return self.st['Final Lowerband']
        
    def super_trend_direction(self):
        return self.st['Supertrend']

def round_down(n, decimals=0):
    multiplier = 10 ** decimals
    return math.floor(n * multiplier) / multiplier

def black_scholes(option_type, S, K, T, r, sigma):
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = (math.log(S / K) + (r - 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    
    if option_type == "call":
        return 'Call price : {:.3f}'.format(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
    elif option_type == "put":
        return 'Put price : {:.3f}'.format(K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))
    else:
        return None

def send_email(receiver, company, langage):
    company_name = company
    sender = os.getenv('EMAIL')
    password_email = os.getenv('EMAIL_PASSWORD')
    receiver_name = receiver
    langage = langage

    if receiver == 'skender':
        receiver_name = os.getenv('EMAIL')
    
    if langage == 'fr':
        with open("email_corporate_fr.txt", "r", encoding='utf-8') as f:
            email_text = f.read()
    elif langage == 'en':
        with open("email_corporate_en.txt", "r", encoding='utf-8') as f:
            email_text = f.read()
    else :
        print('Langage not supported')


    modified_email_text = email_text.replace("[ENTREPRISE]", company_name)

    msg = MIMEText(modified_email_text, 'plain', 'utf-8')
    msg['From'] = sender
    msg['To'] = receiver_name
    msg['Subject'] = 'Lettre de motivation {}'.format(company_name)

    smtp = smtplib.SMTP('smtp.gmail.com', 587)
    smtp.starttls()

    # login with your credentials
    smtp.login(sender, password_email)

    # send email
    smtp.sendmail(sender, receiver_name, msg.as_bytes())

    # terminate SMTP session
    smtp.quit()