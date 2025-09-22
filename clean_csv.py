# Python script to clean the abc.csv file
import csv

input_file = 'abc.csv'
output_file = 'cleaned_abc.csv'

with open(input_file, 'r', newline='') as csvfile:
    reader = csv.reader(csvfile)
    rows = list(reader)

cleaned_rows = []
for row in rows:
    # Fix rows with missing quotes
    if len(row) > 4:
        row = [','.join(row[:-3]), row[-3], row[-2], row[-1]]
    # Fix rows with semicolon delimiter
    if ';' in row[0]:
        row = row[0].split(';')
    # Fix non-numeric age
    if not row[2].isdigit():
        row[2] = ''
    cleaned_rows.append(row)

with open(output_file, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerows(cleaned_rows)
