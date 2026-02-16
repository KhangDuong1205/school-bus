import pandas as pd
import os

file_path = r'c:\Users\024792\Downloads\school-bus\student-data\swat XCL dan test upload - Sheet1.csv'

# Read the CSV file
try:
    df = pd.read_csv(file_path)
    print(f"Successfully read {file_path}")
except Exception as e:
    print(f"Error reading file: {e}")
    exit(1)

# Generate new IDs
# Assuming we want IDs like S001, S002, ...
new_ids = [f'S{i+1:03d}' for i in range(len(df))]

# Update the 'ID' column
# Verify if 'ID' column exists, if not, create it or use the first column if it's the intended ID column but named differently
if 'ID' in df.columns:
    df['ID'] = new_ids
else:
    # If ID column doesn't exist by name, maybe it's the first column based on the user request saying "it is now containing name"
    # We will force the first column to be the ID column as per user intent "change the entire student id column"
    # The view_file output showed the first column header is 'ID' and values are names.
    # So df['ID'] should work if pandas read it correctly.
    print("Column 'ID' not found, attempting to use the first column.")
    df.iloc[:, 0] = new_ids
    # Rename the first column to 'ID' just in case
    df.rename(columns={df.columns[0]: 'ID'}, inplace=True)


# Save the updated CSV
try:
    df.to_csv(file_path, index=False)
    print(f"Successfully updated IDs in {file_path}")
    print("First 5 rows of updated IDs:")
    print(df[['ID', "Sender's first name"]].head()) # Show ID and name for verification
except PermissionError:
    print(f"Permission denied for {file_path}. The file might be open.")
    new_file_path = file_path.replace('.csv', '_updated.csv')
    try:
        df.to_csv(new_file_path, index=False)
        print(f"Successfully saved updated IDs to new file: {new_file_path}")
        print("First 5 rows of updated IDs:")
        print(df[['ID', "Sender's first name"]].head())
    except Exception as e:
        print(f"Error saving to new file: {e}")
        exit(1)
except Exception as e:
    print(f"Error saving file: {e}")
    exit(1)
