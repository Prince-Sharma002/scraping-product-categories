import sys
import time

def scrape_keyword(keyword):
    print(f"  [Scraper Tool] Pretending to scrape data for: '{keyword}'")
    # Simulate some scraping time
    time.sleep(0.5)
    print(f"  [Scraper Tool] Successfully scraped: '{keyword}'\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        kw = sys.argv[1]
        scrape_keyword(kw)
    else:
        print("Please provide a keyword to scrape.")
