#!/usr/bin/env python3
"""
Nepali Dictionary SQLite to DSL Converter
Converts the Nepali dictionary SQLite database to DSL format for KOReader
"""

import sqlite3
import argparse
from pathlib import Path

class NepaliDictConverter:
    def __init__(self):
        # Common part-of-speech mappings from Nepali abbreviations to full forms
        self.pos_mappings = {
            'नि.': 'निपात (particle)',
            'एक. क्रि.': 'एकर्मक क्रिया (transitive verb)',
            'अ. क्रि.': 'अकर्मक क्रिया (intransitive verb)',
            'क्रि.': 'क्रिया (verb)',
            'सङ्. ना.': 'संज्ञा नाम (proper noun)',
            'ना.': 'नाम (noun)',
            'वि.': 'विशेषण (adjective)',
            'क्रि. वि.': 'क्रिया विशेषण (adverb)',
            'सर्व.': 'सर्वनाम (pronoun)',
            'अव्य.': 'अव्यय (indeclinable)',
            'सं.': 'संज्ञा (noun)',
            'N/A': ''
        }

    
    def explore_database(self, db_path):
        """Explore the structure of the SQLite database"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables in database: {[table[0] for table in tables]}")
        
        for table_name in [table[0] for table in tables]:
            print(f"\n--- Table: {table_name} ---")
            
            # Get column info
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            print("Columns:", [col[1] for col in columns])
            
            # Get sample data
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 5;")
            samples = cursor.fetchall()
            print("Sample data:")
            for i, row in enumerate(samples, 1):
                print(f"  {i}. {row}")
            
            # Get count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            count = cursor.fetchone()[0]
            print(f"Total records: {count}")
        
        conn.close()
    
    def extract_dictionary_entries(self, db_path):
        """Extract complete dictionary entries with definitions and examples"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Query to get all words with their definitions and examples
        query = """
        SELECT 
            w.id as word_id,
            w.value as word,
            w.part_of_speech,
            d.id as def_id,
            d.value as definition,
            GROUP_CONCAT(e.value, ' || ') as examples
        FROM word w
        LEFT JOIN definition d ON w.id = d.word_id
        LEFT JOIN example e ON d.id = e.definition_id
        GROUP BY w.id, d.id
        ORDER BY w.value, d.id
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        
        # Group entries by word
        entries = {}
        
        for row in rows:
            word_id, word, pos, def_id, definition, examples = row
            
            if not word:
                continue
            
            # Initialize word entry if not exists
            if word not in entries:
                entries[word] = {
                    'word_id': word_id,
                    'word': word,
                    'part_of_speech': pos,
                    'definitions': []
                }
            
            # Add definition if it exists
            if definition:
                def_entry = {
                    'definition': definition,
                    'examples': []
                }
                
                # Parse examples
                if examples:
                    example_list = examples.split(' || ')
                    def_entry['examples'] = [ex.strip() for ex in example_list if ex.strip()]
                
                entries[word]['definitions'].append(def_entry)
        
        print(f"Extracted {len(entries)} unique words with definitions")
        return entries
    
    def convert_to_dsl(self, entries, output_file):
        """Convert dictionary entries to DSL format"""
        
        if not entries:
            print("No entries to convert")
            return 0
        
        dsl_lines = []
        
        # DSL header
        dsl_lines.append('#NAME "Nepali Contemporary Dictionary"')
        dsl_lines.append('#INDEX_LANGUAGE "Nepali"') 
        dsl_lines.append('#CONTENTS_LANGUAGE "Nepali"')
        dsl_lines.append('')
        
        processed_count = 0
        
        # Sort entries by Nepali word for better organization
        sorted_entries = sorted(entries.items(), key=lambda x: x[0])
        
        for word, entry_data in sorted_entries:
            try:
                # Start DSL entry with the headword
                dsl_entry_lines = [word]
                
                # Add part of speech if available
                pos = entry_data.get('part_of_speech', '').strip()
                if pos and pos != 'N/A':
                    pos_full = self.pos_mappings.get(pos, pos)
                    if pos_full:
                        dsl_entry_lines.append(f"[i]{pos_full}[/i]")
                
                # Add definitions
                definitions = entry_data.get('definitions', [])
                if definitions:
                    for i, def_data in enumerate(definitions, 1):
                        definition = def_data.get('definition', '').strip()
                        if definition:
                            # Number definitions if there are multiple
                            if len(definitions) > 1:
                                dsl_entry_lines.append(f"{i}. {definition}")
                            else:
                                dsl_entry_lines.append(definition)
                            
                            # Add examples if available
                            examples = def_data.get('examples', [])
                            if examples:
                                for example in examples[:2]:  # Limit to 2 examples per definition
                                    if example.strip():
                                        dsl_entry_lines.append(f"   [color=gray]उदाहरण: {example.strip()}[/color]")
                else:
                    # If no definitions, add a placeholder
                    dsl_entry_lines.append("[i]परिभाषा उपलब्ध छैन[/i]")
                
                # Join all lines for this entry
                dsl_entry = '\n'.join(dsl_entry_lines) + '\n'
                dsl_lines.append(dsl_entry)
                processed_count += 1
                
            except Exception as e:
                print(f"Error processing entry {word}: {e}")
                continue
        
        # Write DSL file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(dsl_lines))
        
        print(f"DSL file created: {output_file}")
        print(f"Processed {processed_count} words")
        
        return processed_count

    def show_sample_entries(self, entries, count=5):
        """Show sample entries for verification"""
        print(f"\n--- Sample Entries (first {count}) ---")
        
        sample_words = list(entries.keys())[:count]
        for i, word in enumerate(sample_words, 1):
            entry = entries[word]
            print(f"\n{i}. Word: {word}")
            print(f"   Part of Speech: {entry.get('part_of_speech', 'N/A')}")
            print(f"   Definitions: {len(entry.get('definitions', []))}")
            
            # Show first definition and example
            definitions = entry.get('definitions', [])
            if definitions:
                first_def = definitions[0]
                definition = first_def.get('definition', '')[:80]
                print(f"   First Definition: {definition}{'...' if len(first_def.get('definition', '')) > 80 else ''}")
                
                examples = first_def.get('examples', [])
                if examples:
                    example = examples[0][:60]
                    print(f"   Example: {example}{'...' if len(examples[0]) > 60 else ''}")

def main():
    parser = argparse.ArgumentParser(description='Convert Nepali dictionary SQLite to DSL format')
    parser.add_argument('--explore', help='Explore database structure (provide db file path)')
    parser.add_argument('--convert', help='Convert database to DSL (provide db file path)')
    parser.add_argument('-o', '--output', help='Output DSL file name', default='nepali_dictionary.dsl')
    parser.add_argument('--sample', action='store_true', help='Show sample entries before converting')
    
    args = parser.parse_args()
    
    converter = NepaliDictConverter()
    
    if args.explore:
        db_path = Path(args.explore)
        if not db_path.exists():
            print(f"Database file not found: {db_path}")
            return
        
        converter.explore_database(db_path)
    
    elif args.convert:
        db_path = Path(args.convert)
        if not db_path.exists():
            print(f"Database file not found: {db_path}")
            return
        
        print("Extracting dictionary entries...")
        entries = converter.extract_dictionary_entries(db_path)
        
        if not entries:
            print("No entries found in database")
            return
        
        if args.sample:
            converter.show_sample_entries(entries)
            response = input("\nProceed with conversion? (y/N): ")
            if response.lower() != 'y':
                print("Conversion cancelled")
                return
        
        print(f"\nConverting {len(entries)} entries to DSL format...")
        count = converter.convert_to_dsl(entries, args.output)
        print(f"\nConversion complete! {count} entries written to {args.output}")
        
        # Show file size and first few lines
        output_path = Path(args.output)
        if output_path.exists():
            size_kb = output_path.stat().st_size / 1024
            print(f"File size: {size_kb:.1f} KB")
            
            print("\nFirst few lines of DSL file:")
            with open(output_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= 10:
                        print("...")
                        break
                    print(f"  {line.rstrip()}")
    
    else:
        print("Use --explore to examine the database or --convert to create DSL")
        print("Example usage:")
        print(f"  python {__file__} --explore nep_dict.sqlite3")
        print(f"  python {__file__} --convert nep_dict.sqlite3 --sample")
        print(f"  python {__file__} --convert nep_dict.sqlite3 -o my_nepali_dict.dsl")

if __name__ == '__main__':
    main()