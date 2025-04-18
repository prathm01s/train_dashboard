#!/bin/bash

# Path to your Python file
PYTHON_FILE="ml.py"

# Run the file 10 times
for i in {1..10}
do
  #echo "Run #$i"
  python3 "$PYTHON_FILE"
  #echo "----------------------"
done

