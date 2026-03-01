#!/bin/bash

KEYWORD_FILE=$1

echo "Running scraper for $KEYWORD_FILE"

while read keyword; do
    python3 scrape.py "$keyword"
done < "$KEYWORD_FILE"
