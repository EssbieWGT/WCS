#This script will pull OG data from a single GA and put into a csv file 
#python ./scripts/ogpre.py

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import feedparser
import pandas as pd
import html
from tqdm import tqdm
import datetime
import os
import sys
import json

##############################
###### DEFINE VARIABLES ###### 
##############################

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        # Retrieve the RSS URL from the command line
        filepath = sys.argv[1]
        tsPath = sys.argv[2] 
        rss_url = sys.argv[3]
        savepath = sys.argv[4]
    else: 
        print("Not enough variables passed")

##############################
###### DEFINE FUNCTIONS ###### 
##############################

#check if output file exists. If it does add new data and de-dupe. 
def process_csv(filepath, new_data, savepath):
    """
    Checks if a CSV file exists, creates it if not, adds new data,
    and removes duplicate data based on 'url', keeping the earliest 'firstEyes'.
    Args:
        filepath (str): The path to the CSV file.
        new_data (list): A list of dictionaries representing the new data.
    """
    try:
        if not os.path.exists(filepath):
            # Create a new DataFrame and save it as CSV
            df = pd.DataFrame(new_data)
            df.to_csv(filepath, index=False)
            print(f"CSV file created at: {filepath}")
            return #Exit early.
        # Open the CSV file
        df = pd.read_csv(filepath)
        # Append new data
        new_df = pd.DataFrame(new_data)
        df = pd.concat([df, new_df], ignore_index=True)
        # Remove duplicates, keeping the earliest 'firstEyes'
        if not df.empty: #Only attempt this if the dataframe is not empty.
            df['firstEyes'] = pd.to_datetime(df['firstEyes'],format='ISO8601') #Ensure firstEyes is a datetime object.
            df = df.sort_values('firstEyes')
            df = df.drop_duplicates(subset='url', keep='first') #keep first instance.
            df = df.sort_values(by="published", ascending=False)
            df = df.reset_index(drop=True)
        # Save the updated DataFrame back to CSV
        df.to_csv(filepath, index=False)
        #filter to just things published in the past week, 2025-02-26T15:09:06Z
        # Filter to entries published in the last 7 days
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        dfWeek = df[df['published'] >= seven_days_ago]
        dfWeek = dfWeek.sort_values(by='published', ascending=False).reset_index(drop=True)
        # Save the updated DataFrame
        dfWeek.to_csv(savepath, index=False)
        print(f"CSV file updated at: {filepath}")
    except Exception as e:
        print(f"Error processing CSV file: {e}")

#function to clean up the string to remove HTML tags and special characters 
def clean_and_convert_to_utf8(html_string):
    """
    Removes <b> tags, unescapes HTML entities, and converts to UTF-8.

    Args:
        html_string (str): The HTML string to process.

    Returns:
        str: The cleaned and UTF-8 encoded string.
    """
    try:
        # 1. Remove <b> tags using BeautifulSoup
        soup = BeautifulSoup(html_string, "html.parser")
        for b_tag in soup.find_all("b"):
            b_tag.unwrap()  # Removes the tag but keeps the inner content
        # 2. Unescape HTML entities
        unescaped_text = html.unescape(str(soup)) # Convert soup back to string.
        # 3. Convert to UTF-8, handling potential encoding issues
        utf8_string = unescaped_text.encode('utf-8', errors='replace').decode('utf-8')
        return utf8_string
    except Exception as e:
        print(f"Error processing string: {e}")
        # return None

#remove articles already identified before passing to get_link_preview
def deduplicate_list_with_dataframe(list_of_dicts, dataframe_path, url_key='url', link_column='link'):
    """
    Deduplicates a list of dictionaries against a pandas DataFrame based on URL matching.
    Checks if the dataframe file exists before attempting deduplication.
    Args:
        list_of_dicts: A list of dictionaries, where each dictionary contains a URL.
        dataframe_path: The file path to the pandas DataFrame CSV file.
        url_key: The key in the dictionaries that holds the URL.
        link_column: The name of the DataFrame column that holds the URLs.
    Returns:
        A new list of dictionaries with duplicates removed, or the original list if the file doesn't exist.
    """
    if not os.path.exists(dataframe_path):
        print(f"DataFrame file not found at: {dataframe_path}. Skipping deduplication.")
        return list_of_dicts
    try:
        dataframe = pd.read_csv(dataframe_path)
        dataframe_links = set(dataframe[link_column].astype(str))
        deduplicated_list = [
            item for item in list_of_dicts if item.get(url_key) not in dataframe_links
        ]
        return deduplicated_list
    except (FileNotFoundError, pd.errors.EmptyDataError, Exception) as e:
        print(f"An error occurred: {e}. Skipping deduplication.")
        return list_of_dicts

#get the link preview, and if not available, just use the original content from the RSS entry. 
def get_link_preview(i):
    url = i['link']
    """Fetches and extracts metadata for a link preview."""
    mobile_user_agent = "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36"
    headers = {
        "User-Agent": mobile_user_agent,
    }
    try:
        response = requests.get(url, headers=headers, timeout=15) # Added timeout to avoid long waits.
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(response.content, "html.parser")
        title = soup.find("meta", property="og:title") or soup.find("title")
        description = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        image = soup.find("meta", property="og:image")
        siteName = soup.find("meta", property="og:site_name")
        return {
            "published": i['date'],
            "siteName": siteName["content"] if siteName else urlparse(url).netloc,
            "title": title["content"] if title else i['title'], # If title not found, use domain.
            "description": description["content"] if description else i['summary'],
            "image": image["content"] if image else "",
            "url": url,
            "firstEyes": timestamp
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
        return {
            "published": i['date'],
            "siteName": urlparse(url).netloc,
            "title": i['title'], # If title not found, use domain.
            "description": i['summary'],
            "image": "",
            "url": url,
            "firstEyes": timestamp
        }
    except Exception as general_exception:
        print(f"General Error: {general_exception}")
        return {
            "published": i['date'],
            "siteName": urlparse(url).netloc,
            "title": i['title'], # If title not found, use domain.
            "description": i['summary'],
            "image": "",
            "url": url,
            "firstEyes": timestamp
        }


#append the log so we can track how many new entries we're getting with each run 
def append_to_json_file(tsPath, new_data):
    """Appends new data to a JSON file, or creates and writes if the file does not exist."""
    # Step 1: Read existing data (if the file exists)
    if os.path.exists(tsPath):
        with open(tsPath, 'r') as json_file:
            try:
                tsUse = json.load(json_file)  # Load existing content
            except json.JSONDecodeError:
                tsUse = []  # If the file is empty or invalid, start fresh
    else:
        tsUse = []
    # Step 2: Append new data (assuming tsUse is a list)
    if isinstance(tsUse, dict):  # Convert dict to list if needed
    tsUse = [tsUse]
    tsUse.append(new_data)
    # Step 3: Write updated data back to file
    with open(tsPath, 'w') as json_file:  # 'w' mode writes the updated content
        json.dump(tsUse, json_file, indent=4)


################################################
##### Fetch the most recent data and clean #####
################################################
now = datetime.datetime.now()
timestamp = now.isoformat()
feed = feedparser.parse(rss_url)

entries = []
for entry in feed.entries:
    entries.append({
        "title": entry.title,
        "link": entry.link,
        "date": entry.date,
        "summary": entry.summary,
    })

for item in entries:
    if "link" in item and "&url=" in item['link']:
        item["link"] = item["link"].split("&url=")[-1]

for item in entries:
    if "link" in item and "&ct=" in item['link']:      
        item["link"] = item["link"].split("&ct=")[0]

for item in entries: 
    if "title" in item:
        item['title'] = clean_and_convert_to_utf8(item["title"])

for item in entries: 
    if "title" in item:
        item['title'] = clean_and_convert_to_utf8(item["title"])

for item in entries: 
    if "summary" in item:
        item['summary'] = clean_and_convert_to_utf8(item["summary"])

#this is where you should dedupe, to minimize the URL calls
entries = deduplicate_list_with_dataframe(entries, filepath, url_key='link', link_column='url')

#create timestamp to mark when an item was first observed 
tsUse = {"timestamp": timestamp, "entries": len(entries)}

#if entries has nothing in it, kill the script. 
if len(entries) == 0:
    print("No new content. Exiting script.")
    append_to_json_file(tsPath, tsUse)
    sys.exit()

#fetch the OG data, and put into csv 
outPut = [get_link_preview(value) for value in tqdm(entries)]
dfNew = pd.DataFrame(outPut)
process_csv(filepath, dfNew, savepath)
append_to_json_file(tsPath, tsUse)
print("Added " , len(entries), " new entries")