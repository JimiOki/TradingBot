# 🧠 Algorithmic Trading Development Environment Setup

## Overview

This document describes the setup of a local Python-based algorithmic trading development environment.

The goal is to create a **clean, reproducible, data-driven research environment** that supports:

* Strategy development
* Backtesting
* Data engineering workflows
* Future integration with broker APIs (e.g. IG)
* Optional scaling to cloud (Azure)

---

# 🧱 Core Principles

* **Isolation** → Each project uses its own virtual environment
* **Reproducibility** → Dependencies are controlled and repeatable
* **Simplicity first** → Avoid overengineering early
* **Data-first mindset** → Treat trading like a data platform

Python virtual environments provide isolated environments for dependencies, preventing conflicts between projects ([Real Python][1]).

---

# 🖥️ System Setup

## Installed Tools

* Python 3.11
* Visual Studio Code
* Git
* Windows PowerShell

---

# 📁 Project Structure

Root directory:

```
C:\Dev\trading-lab
```

Structure:

```
trading-lab/
│
├── .env
├── .gitignore
│
├── data/
├── notebooks/
├── strategies/
├── backtests/
├── execution/
├── scripts/
├── logs/
├── config/
```

---

# 🐍 Python Virtual Environment

## Create environment

```
python -m venv .venv
```

## Activate (Windows)

```
.\.venv\Scripts\Activate.ps1
```

## Why this matters

* Keeps dependencies isolated
* Avoids version conflicts
* Ensures reproducibility across machines ([Medium][2])

---

# 📦 Installed Packages

## Core stack

```
pandas
numpy
matplotlib
scikit-learn
```

## Trading & data

```
yfinance
ta
backtrader
```

## Storage

```
pyarrow
fastparquet
```

## Notebook support

```
jupyterlab
ipykernel
```

## Utilities

```
requests
python-dotenv
polars
black
ruff
```

---

# 📊 Parquet Support (Important)

Pandas requires an external engine for Parquet:

* ✅ pyarrow (recommended)
* alternative: fastparquet

Install:

```
pip install pyarrow
```

This enables:

* Efficient data storage
* Columnar format (same concept as Synapse / Data Lake)

---

# 📓 Jupyter Integration

## Register environment

```
python -m ipykernel install --user --name trading-lab --display-name "Python (trading-lab)"
```

## Purpose

* Allows notebooks to use the project environment
* Avoids “module not found” errors across environments

---

# 🔐 Environment Variables

## Location

```
C:\Dev\trading-lab\.env
```

## Example

```
IG_API_KEY=
IG_USERNAME=
IG_PASSWORD=
IG_ACCOUNT_ID=
```

## Usage

```python
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("IG_API_KEY")
```

## Important

`.env` must be excluded from Git:

```
.env
```

---

# 🧪 Sanity Check Script

Location:

```
scripts/sanity_check.py
```

Purpose:

* Validate environment
* Download market data
* Save to Parquet

Example workflow:

1. Download data via `yfinance`
2. Store as `.parquet`
3. Confirm schema and output

---

# 🧹 Code Quality Tools

## Black (formatter)

* Enforces consistent code style
* Removes formatting debates

Run:

```
black .
```

---

## Ruff (linter)

* Detects bugs
* Removes unused imports
* Enforces best practices

Run:

```
ruff check . --fix
```

---

# 🔁 Development Workflow

Typical loop:

1. Activate environment
2. Run scripts / notebooks
3. Fix issues with Ruff
4. Format with Black
5. Commit changes

---

# 🧠 Key Learnings

## 1. Python environments are isolated

Each project has its own:

* Python interpreter
* Packages
* configuration

---

## 2. “Module not found” = wrong environment

Fix by:

* activating `.venv`
* installing packages inside it

---

## 3. Data engineering mindset applies

You are effectively building:

* Local “data lake” (Parquet files)
* Feature pipelines (future)
* Strategy evaluation layer

---

## 4. Jupyter requires explicit kernel linking

Without `ipykernel`, notebooks won’t see your environment.

---

# ⚠️ Common Issues Encountered

## Missing package

```
ModuleNotFoundError: No module named 'pandas'
```

Fix:

```
python -m pip install pandas
```

---

## Parquet engine missing

```
ImportError: Unable to find a usable engine
```

Fix:

```
pip install pyarrow
```

---

## ipykernel missing

Fix:

```
pip install ipykernel
```

---

# 🚀 Next Steps

## Immediate

* Load multiple instruments
* Store locally in Parquet
* Build first simple strategy (e.g. moving average)

## Near-term

* Add backtesting framework
* Introduce feature engineering
* Add ML filtering layer

## Later

* Integrate IG API
* Introduce execution service (C# optional)
* Move components to Azure

---

# 🧠 Final Thought

This setup is not just a “trading bot environment”.

It is:

> A **data-driven research platform for financial experimentation**

Your advantage will come from:

* fast iteration
* clean data
* disciplined testing

—not from complexity.

---

[1]: https://realpython.com/python-virtual-environments-a-primer/?utm_source=chatgpt.com "Python Virtual Environments: A Primer"
[2]: https://medium.com/%40techwithjulles/mastering-pythons-virtual-environments-a-step-by-step-guide-8b4577223369?utm_source=chatgpt.com "Mastering Python's Virtual Environments: A Step-by- ..."
