import sys
import json
import pandas as pd
import ta
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, QPushButton, 
                             QComboBox, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QSpacerItem, QSizePolicy, QSpinBox, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from pybit.unified_trading import HTTP
import time

# Define the Worker class
class Worker(QThread):
    # Define signals to communicate with GUI
    balance_updated = pyqtSignal(float)
    price_updated = pyqtSignal(float)
    ordered_price_updated = pyqtSignal(float)
    positions_updated = pyqtSignal(list)
    profit_loss_updated = pyqtSignal(float)
    bot_status_updated = pyqtSignal(str)
    all_positions_updated = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, bot_state):
        super().__init__()
        self.bot_state = bot_state
        self.is_running = True
        self.is_bot_active = False
        # Initialize API session
        self.session = HTTP(
            testnet=True,
            api_key='s4GwlJ1bhBbju2tRKB',
            api_secret='BBaMzoXaimeyx4GkAEYDNyGrHlT2zGchKYiH',
            demo=True
        )
        self.max_pos = 5

    def run(self):
        while self.is_running:
            try:
                # Update bot state
                bot_state = self.bot_state

                # Fetch balance
                balance = self.get_balance()
                if balance is not None:
                    self.balance_updated.emit(balance)
                    self.bot_state['availableBalance'] = balance
                else:
                    self.error_occurred.emit("Failed to fetch balance.")
                    self.balance_updated.emit(0.0)

                # Fetch current price
                current_price = self.get_current_price(bot_state['pair'])
                if current_price is not None:
                    self.price_updated.emit(current_price)
                    self.bot_state['price'] = current_price
                else:
                    self.error_occurred.emit("Failed to fetch current price.")
                    self.price_updated.emit(0.0)
                
                # Fetch ordered price
                ordered_price = self.get_ordered_price(bot_state['pair'])

                if ordered_price is not None:
                    self.ordered_price_updated.emit(ordered_price)
                    self.bot_state['ordered_price'] = ordered_price
                else:
                    self.error_occurred.emit("Failed to fetch ordered price.")
                    self.ordered_price_updated.emit(0.0)

                # Fetch positions
                positions = self.get_positions()
                self.positions_updated.emit(positions)
                self.bot_state['position'] = positions

                # Fetch all positions detailed
                all_positions = self.get_all_positions()
                self.all_positions_updated.emit(all_positions)
                self.bot_state['all_position'] = all_positions

                # Fetch PnL
                pnl = self.get_pnl()
                self.profit_loss_updated.emit(pnl)
                self.bot_state['profitLoss'] = pnl

                if self.is_bot_active:
                    # Perform trading logic
                    self.perform_trading_logic()

                time.sleep(5)  # Wait for 5 seconds before next update
            except Exception as e:
                self.error_occurred.emit(str(e))
                time.sleep(5)

    def stop(self):
        self.is_running = False

    def start_bot(self):
        self.is_bot_active = True
        self.bot_status_updated.emit("Start")
        # self.set_mode()

    def stop_bot(self):
        self.is_bot_active = False
        self.bot_status_updated.emit("Stop")

    def exit_bot(self):
        self.is_bot_active = False
        self.is_running = False
        self.bot_status_updated.emit("Exit")
        self.quit()
        self.wait()

    # Trading functions

    def get_balance(self):
        try:
            resp = self.session.get_wallet_balance(accountType="UNIFIED", coin="USDT")['result']['list']
            if resp:
                # Assuming the first element has the required balance
                balance = resp[0]['coin'][0]['walletBalance']
                return float(balance)
            else:
                return None
        except Exception as err:
            print(f"Error getting balance: {err}")
            self.error_occurred.emit(f"Error getting balance: {err}")
            return None

    def get_tickers(self):
        try:
            resp = self.session.get_tickers(category="linear")['result']['list']
            return [elem['symbol'] for elem in resp if 'USDT' in elem['symbol'] and 'USDC' not in elem['symbol']]
        except Exception as err:
            print(f"Error getting tickers: {err}")
            self.error_occurred.emit(f"Error getting tickers: {err}")
            return []

    def klines(self, limit=500):
        symbol = self.bot_state['pair']
        timeframe = self.bot_state['timeFrame']
        try:
            resp = self.session.get_kline(
                category='linear',
                symbol=symbol,
                interval=timeframe,
                limit=limit
            )['result']['list']
            df = pd.DataFrame(resp, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Turnover'])
            df = df.set_index('Time').astype(float).iloc[::-1]
            return df
        except Exception as err:
            print(f"Error getting klines: {err}")
            self.error_occurred.emit(f"Error getting klines: {err}")
            return pd.DataFrame()

    def get_positions(self):
        try:
            resp = self.session.get_positions(category='linear', settleCoin='USDT')['result']['list']
            pos = [elem['symbol'] for elem in resp]
            return pos
        except Exception as err:
            print(f"Error getting positions: {err}")
            self.error_occurred.emit(f"Error getting positions: {err}")
            return []

    def get_all_positions(self):
        try:
            resp = self.session.get_positions(category='linear', settleCoin='USDT')['result']['list']
            return resp
        except Exception as err:
            print(f"Error getting all positions: {err}")
            self.error_occurred.emit(f"Error getting all positions: {err}")
            return []

    def get_pnl(self):
        try:
            resp = self.session.get_closed_pnl(category="linear", limit=50)['result']['list']
            pnl = sum(float(elem['closedPnl']) for elem in resp)
            return pnl
        except Exception as err:
            print(f"Error getting PnL: {err}")
            self.error_occurred.emit(f"Error getting PnL: {err}")
            return 0.0

    def get_current_price(self, symbol):
        try:
            resp = self.session.get_tickers(category='linear', symbol=symbol)['result']['list'][0]
            return float(resp['markPrice'])
        except Exception as err:
            print(f"Error getting current price: {err}")
            self.error_occurred.emit(f"Error getting current price: {err}")
            return None
    
    def get_ordered_price(self, symbol):
        try:
            # Make the API call to get the order book
            response = self.session.get_orderbook(
                category='linear',
                symbol=symbol,
                limit=1  # Removed orderStatus='Filled' since it doesn't apply here
            )
            
            # Print the full response for debugging
            print(f"response: {response}")

            # Access the bids and asks from the response
            bids = response['result']['b']
            asks = response['result']['a']

            ordered_price = None

            # Check if there are any bids
            if bids:
                # Get the highest bid price
                ordered_price = float(bids[0][0])  # Accessing the first bid's price
                print(f"Highest bid price for {symbol}: {ordered_price}")
            elif asks:
                # If no bids, consider the lowest ask price
                ordered_price = float(asks[0][0])  # Accessing the first ask's price
                print(f"Lowest ask price for {symbol}: {ordered_price}")
            else:
                print(f"No orders found for {symbol}")

            return ordered_price

        except Exception as err:
            print(f"Error getting ordered price: {err}")
            self.error_occurred.emit(f"Error getting ordered price: {err}")
            return None



    def set_mode(self):
        symbol = self.bot_state['pair']
        mode = self.bot_state['mode']
        leverage = self.bot_state['leverage']
        try:
            resp = self.session.switch_margin_mode(
                category='linear',
                symbol=symbol,
                tradeMode=mode,
                buyLeverage=leverage,
                sellLeverage=leverage
            )
            print(f"Set mode response: {resp}")
        except Exception as err:
            print(f"Error setting mode: {err}")
            self.error_occurred.emit(f"Error setting mode: {err}")

    def get_precisions(self, symbol):
        try:
            resp = self.session.get_instruments_info(category='linear', symbol=symbol)['result']['list'][0]
            price_tick = resp['priceFilter']['tickSize']
            price_precision = len(price_tick.split('.')[1]) if '.' in price_tick else 0
            qty_step = resp['lotSizeFilter']['qtyStep']
            qty_precision = len(qty_step.split('.')[1]) if '.' in qty_step else 0
            return price_precision, qty_precision
        except Exception as err:
            print(f"Error getting precisions: {err}")
            self.error_occurred.emit(f"Error getting precisions: {err}")
            return 0, 0

    def place_order_market(self, side):
        symbol = self.bot_state['pair']
        tp = self.bot_state['takeProfit']
        sl = self.bot_state['stopLoss']
        qty = self.bot_state['orderQty']

        price_precision, qty_precision = self.get_precisions(symbol)
        mark_price = self.get_current_price(symbol)

        if mark_price is None:
            self.error_occurred.emit("Cannot place order without current price.")
            return

        try:
            order_qty = round(int(qty) / mark_price, qty_precision)
            tp_price = round(mark_price + mark_price * float(tp), price_precision)
            sl_price = round(mark_price - mark_price * float(sl), price_precision)

            print(f'Placing {side.upper()} order for {symbol} at {mark_price}')
            order_resp = self.session.place_order(
                category='linear',
                symbol=symbol,
                side=side.capitalize(),
                orderType='Market',
                qty=order_qty,
                takeProfit=tp_price,
                stopLoss=sl_price,
                tpTriggerBy='MarkPrice',
                slTriggerBy='MarkPrice'
            )
            print(f'{side.capitalize()} order response: {order_resp}')
        except Exception as err:
            print(f"Error placing order: {err}")
            self.error_occurred.emit(f"Error placing order: {err}")

    def check_ema_20(self):
        kl = self.klines()
        if kl.empty or len(kl) < 20:
            return 'none'
        ema_20 = ta.trend.ema_indicator(kl['Close'], window=20)
        current_price = kl['Close'].iloc[-1]
        previous_price = kl['Close'].iloc[-2]
        current_ema_20 = ema_20.iloc[-1]
        previous_ema_20 = ema_20.iloc[-2]

        if previous_price < previous_ema_20 and current_price > current_ema_20:
            return 'buy'
        elif previous_price > previous_ema_20 and current_price < current_ema_20:
            return 'sell'
        else:
            return 'none'

    def perform_trading_logic(self):
        bot_state = self.bot_state
        pos = bot_state['position']
        symbol = bot_state['pair']

        if len(pos) < self.max_pos:
            ema_signal = self.check_ema_20()
            print(f'EMA signal: {ema_signal}')

            if ema_signal == 'buy' and symbol not in pos:
                print(f'Placing BUY order for {symbol}')
                self.place_order_market('buy')
            elif ema_signal == 'sell' and symbol in pos:
                print(f'Placing SELL order for {symbol}')
                self.place_order_market('sell')

# Define the GUI class
class TradingBotApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trading Bot")
        self.setGeometry(100, 100, 600, 500)

        # Initialize bot state
        self.bot_state = {
            "position": "",
            "availableBalance": "",
            "pair": "BTCUSDT",
            "timeFrame": "1",
            "leverage": 1,
            "mode": "Isolated",
            "orderQty": 0,
            "stopLoss": 0.0,
            "takeProfit": 0.0,
            "trailingStopLoss": 0.0,
            "profitLoss": 0.0,
            "botStatus": "Stopped",
            "price": None,
            "all_position": []
        }

        # Initialize UI
        self.init_ui()

        # Initialize Worker
        self.worker = Worker(self.bot_state)
        # Connect signals
        self.worker.balance_updated.connect(self.update_balance)
        self.worker.price_updated.connect(self.update_price)
        self.worker.ordered_price_updated.connect(self.update_ordered_price)
        self.worker.positions_updated.connect(self.update_positions)
        self.worker.profit_loss_updated.connect(self.update_profit_loss)
        self.worker.bot_status_updated.connect(self.update_bot_status)
        self.worker.all_positions_updated.connect(self.update_all_positions)
        self.worker.error_occurred.connect(self.show_error)

        # Start the worker thread
        self.worker.start()

    def init_ui(self):
        layout = QVBoxLayout()

        grid = QGridLayout()

        # Available Balance
        balance_label = QLabel("Available Balance (in $1000)")
        self.balance_input = QLineEdit()
        self.balance_input.setPlaceholderText("Available Balance (in $1000)")
        self.balance_input.setDisabled(True)
        grid.addWidget(balance_label, 0, 0)
        grid.addWidget(self.balance_input, 0, 1)

        # Pair
        pair_label = QLabel("Pair")
        self.pair_select = QComboBox()
        self.pair_select.addItems(["BTCUSDT", "ETHUSDT"])
        self.pair_select.currentTextChanged.connect(self.on_pair_change)
        grid.addWidget(pair_label, 1, 0)
        grid.addWidget(self.pair_select, 1, 1)

        # Time Frame
        timeframe_label = QLabel("Time Frame")
        self.timeframe_select = QComboBox()
        self.timeframe_select.addItems(["1", "5", "10", "15", "30"])
        self.timeframe_select.currentTextChanged.connect(self.on_time_frame_change)
        grid.addWidget(timeframe_label, 2, 0)
        grid.addWidget(self.timeframe_select, 2, 1)

        # Leverage
        leverage_label = QLabel("Leverage")
        self.leverage_input = QSpinBox()
        self.leverage_input.setRange(1, 100)
        self.leverage_input.setValue(1)
        self.leverage_input.valueChanged.connect(self.on_leverage_change)
        grid.addWidget(leverage_label, 3, 0)
        grid.addWidget(self.leverage_input, 3, 1)

        # Mode
        mode_label = QLabel("Mode")
        self.mode_select = QComboBox()
        self.mode_select.addItems(["Isolated", "Cross"])
        self.mode_select.currentTextChanged.connect(self.on_mode_change)
        grid.addWidget(mode_label, 4, 0)
        grid.addWidget(self.mode_select, 4, 1)

        # Order Quantity
        order_qty_label = QLabel("Order Quantity")
        self.order_qty_input = QSpinBox()
        self.order_qty_input.setRange(0, 10000)
        self.order_qty_input.valueChanged.connect(self.on_order_qty_change)
        grid.addWidget(order_qty_label, 5, 0)
        grid.addWidget(self.order_qty_input, 5, 1)

        # Stop Loss
        stop_loss_label = QLabel("Stop Loss %")
        self.stop_loss_input = QLineEdit()
        self.stop_loss_input.setPlaceholderText("Stop Loss % (e.g., 0.01)")
        self.stop_loss_input.textChanged.connect(self.on_stop_loss_change)
        grid.addWidget(stop_loss_label, 6, 0)
        grid.addWidget(self.stop_loss_input, 6, 1)

        # Take Profit
        take_profit_label = QLabel("Take Profit %")
        self.take_profit_input = QLineEdit()
        self.take_profit_input.setPlaceholderText("Take Profit % (e.g., 0.02)")
        self.take_profit_input.textChanged.connect(self.on_take_profit_change)
        grid.addWidget(take_profit_label, 7, 0)
        grid.addWidget(self.take_profit_input, 7, 1)

        # Trailing Stop Loss (optional)
        tsl_label = QLabel("Trailing Stop Loss %")
        self.tsl_input = QLineEdit()
        self.tsl_input.setPlaceholderText("Trailing Stop Loss %")
        self.tsl_input.textChanged.connect(self.on_tsl_change)
        grid.addWidget(tsl_label, 8, 0)
        grid.addWidget(self.tsl_input, 8, 1)

        # Profit/Loss
        pl_label = QLabel("Profit/Loss")
        self.pl_display = QLabel("0.0")
        self.pl_display.setStyleSheet("color: green")
        grid.addWidget(pl_label, 9, 0)
        grid.addWidget(self.pl_display, 9, 1)

        layout.addLayout(grid)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Bot")
        self.start_button.clicked.connect(self.start_bot)
        self.stop_button = QPushButton("Stop Bot")
        self.stop_button.clicked.connect(self.stop_bot)
        self.exit_button = QPushButton("Exit Bot")
        self.exit_button.clicked.connect(self.exit_bot)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.exit_button)

        layout.addLayout(button_layout)

        # Current Price
        self.current_price_label = QLabel("Current Price: Fetching...")
        layout.addWidget(self.current_price_label)

        # Ordered Price
        self.ordered_price_label = QLabel("Ordered Price: 0.0")
        layout.addWidget(self.ordered_price_label)

        # Bot Status
        self.bot_status_label = QLabel("Bot Status: Stopped")
        layout.addWidget(self.bot_status_label)

        # Set layout
        self.setLayout(layout)

    # Slot functions to update bot state
    def on_pair_change(self, text):
        self.bot_state['pair'] = text

    def on_time_frame_change(self, text):
        self.bot_state['timeFrame'] = text

    def on_leverage_change(self, value):
        self.bot_state['leverage'] = value

    def on_mode_change(self, text):
        self.bot_state['mode'] = text

    def on_order_qty_change(self, value):
        self.bot_state['orderQty'] = value

    def on_stop_loss_change(self, text):
        try:
            self.bot_state['stopLoss'] = float(text)
        except ValueError:
            self.bot_state['stopLoss'] = 0.0

    def on_take_profit_change(self, text):
        try:
            self.bot_state['takeProfit'] = float(text)
        except ValueError:
            self.bot_state['takeProfit'] = 0.0

    def on_tsl_change(self, text):
        try:
            self.bot_state['trailingStopLoss'] = float(text)
        except ValueError:
            self.bot_state['trailingStopLoss'] = 0.0

    # Slot functions to update GUI
    def update_balance(self, balance):
        self.balance_input.setText(f"{balance:.2f}")
        self.bot_state['availableBalance'] = balance

    def update_price(self, price):
        self.current_price_label.setText(f"Current Price: ${price:.2f}")
        self.bot_state['price'] = price

    def update_ordered_price(self, price):
        self.ordered_price_label.setText(f"Ordered Price: {price:.2f}")

    def update_positions(self, positions):
        self.bot_state['position'] = positions
        # Implement position display if needed

    def update_all_positions(self, all_positions):
        self.bot_state['all_position'] = all_positions
        # Implement detailed position display if needed

    def update_profit_loss(self, pnl):
        self.pl_display.setText(f"{pnl:.2f}")
        if pnl >= 0:
            self.pl_display.setStyleSheet("color: green")
        else:
            self.pl_display.setStyleSheet("color: red")
        self.bot_state['profitLoss'] = pnl

    def update_bot_status(self, status):
        self.bot_status_label.setText(f"Bot Status: {status}")

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)

    # Button actions
    def start_bot(self):
        # Validate inputs
        if (self.bot_state['orderQty'] == 0 or
            self.bot_state['availableBalance'] == "" or
            self.bot_state['stopLoss'] == 0.0 or
            self.bot_state['takeProfit'] == 0.0):
            QMessageBox.warning(self, "Input Error", "Order Qty, Available Balance, Stop Loss, and Take Profit are required.")
            return

        # Start the bot
        self.worker.start_bot()
        self.start_button.setDisabled(True)
        self.stop_button.setEnabled(True)
        self.bot_status_label.setText("Bot Status: Start")
        print("Bot started with state:", self.bot_state)

    def stop_bot(self):
        self.worker.stop_bot()
        self.start_button.setEnabled(True)
        self.stop_button.setDisabled(True)
        self.bot_status_label.setText("Bot Status: Stop")
        print("Bot stopped")

    def exit_bot(self):
        self.worker.exit_bot()
        self.close()

    def closeEvent(self, event):
        # When closing the window, stop the worker
        self.worker.exit_bot()
        event.accept()

def main():
    app = QApplication(sys.argv)
    bot_app = TradingBotApp()
    bot_app.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
