#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import re
import sys

def scrape_kantipur_article(url):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Kantipur article selector (adjust for other sites)
        article_content = soup.find('div', class_='current-news-block')
        if not article_content:
            article_content = soup.find('div', class_='description')
        
        if article_content:
            paragraphs = article_content.find_all('p')
            sentences = []
            for p in paragraphs:
                text = p.get_text().strip()
                if text and len(text) > 20:  # Filter out short fragments
                    # Split into sentences (basic Nepali sentence splitting)
                    sent_list = re.split(r'[।!?]', text)
                    for sent in sent_list:
                        sent = sent.strip()
                        if len(sent) > 15:  # Reasonable sentence length
                            sentences.append(sent + '।')
            return sentences
        return []
    except Exception as e:
        print(f"Error scraping: {e}")
        return []

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scrape_nepali.py <URL>")
        return
    
    url = sys.argv[1]
    sentences = scrape_kantipur_article(url)
    
    if sentences:
        print(f"Found {len(sentences)} sentences:")
        for i, sentence in enumerate(sentences, 1):
            print(f"{i}. {sentence}")
        
        # Save to file
        with open('/tmp/scraped_sentences.txt', 'w', encoding='utf-8') as f:
            for sentence in sentences:
                f.write(f"{sentence}\t[TRANSLATION]\t{url}\n")
        
        print(f"\n✓ Saved to /tmp/scraped_sentences.txt")
    else:
        print("No sentences found")

if __name__ == "__main__":
    main()