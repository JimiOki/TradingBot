# Trading Lab — Glossary

A plain-English reference for technical terms used across the requirements and architecture documents.

---

## Trading Terms

**Bar**
A single unit of price data for a time period. A daily bar contains the open, high, low, close, and volume for one trading day. Also called a candlestick.

**OHLCV**
Open, High, Low, Close, Volume — the five standard fields in a price bar.

**Signal**
An instruction produced by a strategy. Values are: `1` (go long / buy), `-1` (go short / sell), `0` (do nothing / flat).

**Long**
Buying an instrument expecting the price to rise. You profit if it goes up.

**Short**
Selling an instrument you don't own, expecting the price to fall. You profit if it goes down. IG spreadbetting makes this straightforward — you just bet on the price going down.

**Flat**
Having no open position in an instrument.

**Spreadbetting**
A way of trading where you bet on whether a price will go up or down, in pounds per point of movement. No stamp duty, losses are tax-deductible against spreadbet profits, and you can go long or short easily.

**Position**
An open trade. A long position in Gold means you currently have a live bet that Gold will rise.

**Position Sizing**
Deciding how much money to risk on a trade. For example, risking 1% of your capital per trade.

**Stop Loss**
A price level at which a trade is automatically closed to limit your loss.

**Take Profit**
A price level at which a trade is automatically closed to lock in your gain.

**Risk/Reward Ratio**
The ratio of potential loss to potential gain on a trade. A 1:3 ratio means you risk £1 to potentially make £3.

**Drawdown**
The percentage drop from a peak value to a trough. Maximum drawdown is the largest such drop over a period — a key measure of strategy risk.

**Sharpe Ratio**
A measure of return relative to risk. Higher is better. Above 1.0 is acceptable, above 2.0 is strong for a systematic strategy.

**Win Rate**
The percentage of trades that are profitable. A high win rate does not mean a good strategy — you also need to consider how much you win vs lose per trade.

**Holding Period**
How long a trade stays open. Days-to-weeks means you are a swing trader, not a day trader.

**Equity Curve**
A chart showing how your account value changes over time as trades open and close. Used to visually assess strategy performance.

---

## Strategy & Indicator Terms

**SMA (Simple Moving Average)**
The average closing price over a set number of days. A 50-day SMA is the average of the last 50 closes. Used to identify trend direction.

**SMA Crossover**
A signal generated when a short-term SMA crosses a long-term SMA. For example, when the 50-day SMA crosses above the 200-day SMA — often interpreted as a buy signal.

**RSI (Relative Strength Index)**
A momentum indicator scored 0–100. Above 70 suggests overbought (price may fall), below 30 suggests oversold (price may rise). Used here as a filter to suppress low-quality signals.

**RSI Filter**
Using RSI to suppress a signal. For example, if SMA crossover says buy but RSI is above 70, the signal is blocked because the instrument is already overbought.

**MACD (Moving Average Convergence Divergence)**
An indicator that shows the relationship between two moving averages. Used to spot momentum and trend changes.

**Indicator Overlay**
Drawing an indicator (like SMA or RSI) on top of a price chart so you can see both together.

**Lookahead Bias**
A backtest error where future data is accidentally used to make a past decision. Makes backtest results look better than real-world performance would be. Must be explicitly prevented.

---

## Data Terms

**Ingestion**
The process of fetching data from a source (e.g. yfinance) and saving it locally.

**Normalisation**
Converting raw data into a consistent, clean format — same column names, same timezone, same data types — regardless of source.

**Parquet**
A file format for storing tabular data efficiently. Like a very efficient spreadsheet. Used instead of CSV because it is faster to read and preserves data types.

**Schema**
The structure of a dataset — what columns exist, what type each column is (date, number, text), and what the values mean.

**Curated Data**
Data that has been cleaned, normalised, and validated. Lives in `data/curated/`. Ready for strategies to use.

**Raw Data**
Data exactly as received from the source, before any cleaning. Lives in `data/raw/`.

**UTC (Coordinated Universal Time)**
A universal time standard with no timezone offset. All timestamps in this system are stored in UTC to avoid confusion across markets and daylight saving changes.

**Adjusted Prices**
Historical prices corrected for corporate actions like dividends and stock splits. Important for equity data. Commodities are less affected by this.

**Idempotent**
An operation that produces the same result no matter how many times you run it. Re-running data ingestion should not create duplicates.

**yfinance**
A free Python library that downloads historical price data from Yahoo Finance. Used for research and backtesting. Not suitable for live trading.

---

## System & Architecture Terms

**API (Application Programming Interface)**
A way for two software systems to talk to each other. The IG API lets your bot send orders and receive prices programmatically.

**REST API**
A common style of API that works over standard web requests (HTTP). Used for placing orders, fetching account info, etc.

**Streaming API**
An API that pushes data to you continuously in real time, rather than you having to ask for it each time. Used for live prices and position updates.

**IG Epic**
IG's internal identifier for a tradeable instrument. For example, Gold's IG epic is different from its yfinance ticker `GC=F`. These must be mapped explicitly.

**Demo Account**
A practice account provided by IG with fake money. Uses the identical API to a live account — only the credentials and base URL differ.

**Paper Trading**
Simulating trades without real money. Orders go through the real API (demo account) but no actual money is at risk.

**Kill Switch**
An emergency control that immediately closes all open positions and stops the system from placing new orders. A safety requirement for live trading.

**Streamlit**
A Python library that turns a Python script into a browser-based dashboard. Runs locally on your machine, accessible via browser.

**Tailscale**
A free VPN tool that lets you securely access your home PC from anywhere — including your iPhone — without complex network setup.

**Parquet Engine**
The underlying library that reads and writes Parquet files. This project uses `pyarrow`.

**Virtual Environment (.venv)**
An isolated Python installation for a project. Prevents package version conflicts between different projects on the same machine.

**YAML**
A human-readable file format used for configuration files. Easier to read and edit than JSON. Used for instrument lists, strategy parameters, and environment settings.

**Secrets / Credentials**
Sensitive values like API keys and passwords. Stored in a `.env` file that is never committed to Git.

**.env file**
A local file containing secret credentials. Loaded at runtime by the application. Must be excluded from version control.

**Backtest**
Running a strategy against historical data to see how it would have performed. Not a guarantee of future performance.

**Backtest Artefact**
The saved output of a backtest run — metrics, trade log, equity curve — stored in `data/backtests/`.

**Slippage**
The difference between the price you expected to trade at and the price you actually traded at. Included in backtests to make results more realistic.

**Commission / Fee Model**
The costs of trading (spread, commission) modelled explicitly in the backtest so results are not overstated.

**Non-Functional Requirement (NFR)**
A requirement about how the system behaves rather than what it does. Examples: data must be stored in UTC, secrets must never be committed to Git.

**Acceptance Criteria**
The specific, testable conditions that must be true for a requirement to be considered complete.

**REQ-ID**
A unique identifier for a requirement (e.g. `REQ-DATA-001`). Used to reference requirements precisely without repeating them in full.

---

## Development Terms

**Package (`trading_lab`)**
The core Python library for this project. Contains all reusable strategy, data, and backtest logic. Lives in `src/trading_lab/`.

**Module**
A single Python file within the package. For example, `data/yfinance_ingest.py` is a module responsible for fetching data from yfinance.

**IntelliSense**
VS Code's auto-complete and code suggestion feature. Powered by the Python and Pylance extensions.

**Linter (Ruff)**
A tool that automatically checks your code for errors, bad practices, and unused imports.

**Formatter (Black)**
A tool that automatically rewrites your code to a consistent style. Removes the need to debate formatting conventions.

**GitLens**
A VS Code extension that shows who wrote each line of code and when, inline in the editor.

**WSL2 (Windows Subsystem for Linux 2)**
A feature of Windows that runs a Linux environment inside Windows. Your project runs in WSL2 at `/mnt/c/Dev/trading-lab`.
