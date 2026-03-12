#!/usr/bin/env python3
"""
Legacy Content Migration Script
Parses old_portfolio.html and inserts all projects and experiences into SQLite
"""
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser

# Import from app.py
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import get_db_connection, initialize_database, now_iso

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "portfolio.db"

def extract_text_between(text, start, end):
    """Extract text between two markers"""
    start_idx = text.find(start)
    if start_idx == -1:
        return ""
    start_idx += len(start)
    end_idx = text.find(end, start_idx)
    if end_idx == -1:
        return text[start_idx:].strip()
    return text[start_idx:end_idx].strip()

def parse_html_strong_tags(html_text):
    """Extract key-value pairs from HTML with <strong> tags"""
    pairs = {}
    pattern = r'<p><strong>([^:]+):</strong>\s*(.+?)</p>'
    matches = re.findall(pattern, html_text, re.DOTALL)
    for key, value in matches:
        # Clean HTML tags from value
        clean_value = re.sub(r'<[^>]+>', '', value).strip()
        pairs[key.strip()] = clean_value
    return pairs

def migrate_legacy_content():
    """Parse old_portfolio.html and insert into database"""
    print("Initializing database...")
    initialize_database()
    print("+ Database initialized")
    
    old_html_path = BASE_DIR / "old_portfolio.html"
    
    if not old_html_path.exists():
        print("Error: {} not found".format(old_html_path))
        return False
    
    print("Reading old portfolio HTML...")
    # Try different encodings
    encodings = ['utf-16', 'utf-8', 'latin-1', 'cp1252']
    html_content = None
    for enc in encodings:
        try:
            with open(old_html_path, 'r', encoding=enc) as f:
                html_content = f.read()
            print("+ Read with encoding: {}".format(enc))
            break
        except Exception as e:
            continue
    
    if html_content is None:
        print("Error: Could not decode {}".format(old_html_path))
        return False
    
    conn = get_db_connection()
    cursor = conn.cursor()
    now = now_iso()
    
    # Extract projects
    print("\n=== Migrating Projects ===")
    projects_section = extract_text_between(html_content, 'data-page="projects"', 'data-page="experiences"')
    
    project_items = re.findall(
        r'<li class="project-item active" data-filter-item data-category="([^"]+)" data-projects-item>.*?<h3 class="project-title">([^<]+)</h3>.*?<p class="project-category">([^<]+)</p>.*?<div class="project-description" style="display: none;">(.+?)</div>.*?</li>',
        projects_section,
        re.DOTALL
    )
    
    for category, title, category_display, description_html in project_items:
        pairs = parse_html_strong_tags(description_html)
        
        # Map old field names to database fields
        image_src = re.search(r'<img src="([^"]+)"', description_html)
        image_path = image_src.group(1).replace('../', '') if image_src else ""
        
        try:
            cursor.execute("""
                INSERT INTO portfolio_items 
                (section, category, subsection, title, description, date_label, date_value, 
                 deliverables, challenges, future_improvements, extra_notes, image_path, 
                 external_link, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                'project',
                category.title(),  # e.g., "Web Development"
                '',  # subsection not used for projects
                title,
                pairs.get('Description', ''),
                'Project Timeline',
                "{} - {}".format(pairs.get('Project Start Date', ''), pairs.get('Project End Date', '')),
                pairs.get('Deliverable', ''),
                pairs.get('Challenges Faced', ''),
                pairs.get('Future Improvements', ''),
                "Role: {} | Tech: {}".format(pairs.get('Role', ''), pairs.get('Technologies Used', '')),
                image_path,
                pairs.get('GitHub Repository', ''),
                now,
                now
            ))
            print("+ Added project: {}".format(title))
        except Exception as e:
            print("- Error adding project {}: {}".format(title, e))
    
    # Extract experiences
    print("\n=== Migrating Experiences ===")
    experiences_section = extract_text_between(html_content, 'data-page="experiences"', 'data-page=')
    
    exp_items = re.findall(
        r'<li class="project-item active" data-filter-item data-category="([^"]+)" data-experiences-item>.*?<h3 class="project-title">([^<]+)</h3>.*?<p class="project-category">([^<]+)</p>.*?<div class="project-description" style="display: none;">(.+?)</div>.*?</li>',
        experiences_section,
        re.DOTALL
    )
    
    for subsection, title, subsection_display, description_html in exp_items:
        pairs = parse_html_strong_tags(description_html)
        
        image_src = re.search(r'<img src="([^"]+)"', description_html)
        image_path = image_src.group(1).replace('../', '') if image_src else ""
        
        # Map subsections: events -> Career, certifications -> Certifications, achievements -> Achievements, volunteer/volunteering -> Volunteer
        subsection_map = {
            'events': 'Career',
            'certifications': 'Certifications',
            'achievements': 'Achievements',
            'volunteer': 'Volunteer',
            'volunteering': 'Volunteer'
        }
        subsection_friendly = subsection_map.get(subsection.lower(), subsection)
        
        try:
            cursor.execute("""
                INSERT INTO portfolio_items 
                (section, category, subsection, title, description, date_label, date_value, 
                 deliverables, challenges, future_improvements, extra_notes, image_path, 
                 external_link, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                'experience',
                subsection_friendly,  # Show subsection as category in old format
                subsection_friendly,  # Store original subsection separately
                title,
                pairs.get('Description', ''),
                pairs.get('Certified Date') or pairs.get('Date Awarded') or 'Date',
                pairs.get('Date') or pairs.get('Certified Date') or pairs.get('Date Awarded') or '',
                pairs.get('Deliverable', ''),
                pairs.get('Challenges Faced', ''),
                pairs.get('Future Improvements', ''),
                '',
                image_path,
                '',
                now,
                now
            ))
            print("+ Added experience ({}): {}".format(subsection_friendly, title))
        except Exception as e:
            print("- Error adding experience {}: {}".format(title, e))
    
    conn.commit()
    conn.close()
    
    print("\n+ Migration complete!")
    return True

if __name__ == "__main__":
    migrate_legacy_content()
