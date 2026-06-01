import tempfile
from breachalpha.preprocessor import preprocess_dataset

csv_data = "company_name,breach_date,records_affected,breach_type\nEquifax,2017-09-07,147000000,data_leak\nCapital One,2019-07-29,106000000,data_leak\nMarriott,2018-11-30,500000000,data_leak\n"

with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    f.write(csv_data)
    tmp_path = f.name

result = preprocess_dataset(tmp_path)
print(f"Success: {result.success}")
print(f"DF is None: {result.df is None}")
print(f"Original rows: {result.original_rows}")
print(f"Cleaned rows: {result.cleaned_rows}")
if result.df is not None:
    print(f"DF columns: {list(result.df.columns)}")
    print(f"DF shape: {result.df.shape}")
    print(f"DF head:\n{result.df.head()}")
