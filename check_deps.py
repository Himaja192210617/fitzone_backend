try:
    import pandas
    import sklearn
    from sklearn.ensemble import RandomForestRegressor
    print("SUCCESS: pandas and sklearn are available")
except ImportError as e:
    print(f"FAILURE: {e}")
except Exception as e:
    print(f"ERROR: {e}")
