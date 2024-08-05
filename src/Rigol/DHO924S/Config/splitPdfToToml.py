''' Fill in toml file prompt

Ok so now I'd like your help filling in the toml files based on the data that is already in there. I would like to use these toml files to autogenerate some python to implement my instrument drivers. To do that, I need all of the fields filled in, which I would like your help with. Here are all the classes that I'm planning on adding in:


class Autoset:
    pass
class Acquire:
    pass
class Bus:
    pass
class Bodeplot:
    pass
class Channel:
    pass
class Counter:
    pass
class Cursor:
    pass
class Display:
    pass
class Dvm:
    pass
class Histogram:
    pass
class LogicAnalyzer:
    pass
class Mask:
    pass
class Math:
    pass
class Measure:
    pass
class Record:
    pass
class Reference:
    pass
class Save:
    pass
class Search:
    pass
class Navigate:
    pass
class FunctionGen:
    pass
class Timebase:
    pass
class Trigger:
    pass
class Waveform:
    pass


Could you help me fill in all the "" in this file? Anytime you don't fill in "", just insert "N/A" instead

Could you change the following things?
Commands need to start with ":" and should look similar to what is in the "syntax" field (take the first word/ break at the spaces)
Input_Min and Input_Max should be numbers
Input values should either be discrete values or input types (like float, int, power_of_2)

Could you try that again?
But when there are multiple values in the input_values field, input_min and input_max should be N/A
And the multiple values in the input_values field should be like this: {val1|val2|val3}

'''


import fitz  # Import PyMuPDF
import re
import os
import json
import toml

def extract_headers_from_pdf_by_filename(pdf_path):
    """Extracts headers from the specified PDF file based on the prefix derived from the filename."""
    doc = fitz.open(pdf_path)  # Open the PDF file
    headers = []  # List to hold all headers found
    
    # Extract the prefix from the filename (e.g., '3.12' from '3.12 IEEE488.2 Common Commands.pdf')
    filename = os.path.basename(pdf_path)
    prefix = re.match(r'(\d+\.\d+)', filename).group(1)

    # Regex pattern to identify headers starting with the extracted prefix
    header_pattern = re.compile(r'^' + re.escape(prefix) + r'\.\d+')
    previous_header = ""

    for page in doc:  # Iterate over each page in the PDF
        text = page.get_text("text")  # Extract text from the page
        lines = text.split('\n')  # Split text into lines
        
        for line in lines:
            line = line.strip()
            if header_pattern.match(line):  # Check if the line is a header
                if previous_header:  # If there's a header stored, append it to the list
                    headers.append(previous_header)
                previous_header = line  # Store current line as potential header
            elif previous_header:  # If the previous line was a header, append this line to it
                previous_header += " " + line
                headers.append(previous_header)  # Append the combined header
                previous_header = ""  # Reset for next header

    if previous_header:  # Append the last found header if any
        headers.append(previous_header)

    doc.close()  # Close the document
    return headers

def map_headers_to_pages(pdf_path, headers):
    """Map each header to the first page number it appears on in the PDF."""
    doc = fitz.open(pdf_path)
    header_to_page = {}
    header_pattern = re.compile(r'^(\d+\.\d+\.\d+)\s*(.*)$')  # Updated to capture sub-section numbers and the rest of the header

    for page_num in range(len(doc)):
        page_text = doc[page_num].get_text("text")
        for header in headers:
            # Check for the presence of the section number with potential subsections
            match = header_pattern.match(header)
            if match:
                section_number, header_text = match.groups()
                # Prepare regex pattern to find exact header in the text, considering potential line breaks and excess whitespace
                search_pattern = re.compile(re.escape(section_number) + r'\s+' + re.escape(header_text).replace(r'\ ', r'\s+'))
                if search_pattern.search(page_text):
                    header_to_page[header] = page_num + 1
                    print(f"Header '{header}' found on page {page_num + 1}")
                    break  # Once a header is found, skip to the next header

    doc.close()
    return header_to_page

def pretty_print_details(details):
    print(json.dumps(details, indent=4, sort_keys=False))

def pretty_print_details(details):
    for key, value in details.items():
        print(f"{key}:\n{'-' * len(key)}")
        if isinstance(value, list):
            for item in value:
                print(f"  - {item}")
        else:
            print(f"  {value}\n")

def extract_text_by_header(pdf_path, header, end_header=None):
    doc = fitz.open(pdf_path)
    extracted_text = ""
    capture = False

    # Define function to determine if a line represents a header
    def is_header(line, current_header):
        return line.startswith(current_header.split(' ')[0])  # Check if the line starts with the section number

    # Loop through each page in the document
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if is_header(line, header):
                capture = True
                extracted_text += f"\n{line}\n"  # Start capturing text
            elif capture and (end_header and is_header(line, end_header)):
                break  # Stop capturing if another header is found
            elif capture:
                extracted_text += line + "\n"  # Add text to the captured content

        if capture and end_header and is_header(line, end_header):
            break  # Exit the loop once the end_header is encountered

    doc.close()
    return extracted_text

def remove_footer(texts):
    # Define the regular expression pattern to match the undesired content
    footer_patterns = [
        r'^Command System$',
        r'^DHO800/DHO900 Programming$',
        r'^Guide$',
        r'^[4][0-9]{2}$',  # Matches numbers from 400 to 499
        r'^Copyright ©RIGOL TECHNOLOGIES CO\., LTD\. All rights reserved\.$',
        r'^\s*$'  # Matches empty lines
    ]

    # Combine all patterns into a single pattern with the | (or) operator
    combined_pattern = re.compile('|'.join(footer_patterns), re.MULTILINE)

    cleaned_texts = []
    for partial_text in texts:
        # Remove matched patterns
        cleaned_text = re.sub(combined_pattern, '', partial_text)
        # Optionally, you might want to remove extra new lines left after removal
        cleaned_text = re.sub(r'\n+', '\n', cleaned_text).strip()
        cleaned_texts.append(cleaned_text)
    return cleaned_texts

def list_to_dict(texts):
    result_dict = {}
    for text in texts:
        # Split the text into lines and filter out empty lines
        lines = [line for line in text.split('\n') if line.strip()]
        if len(lines) < 2:
            continue  # Skip entries that do not have at least two lines

        # Use the first two lines as the key
        key = lines[0] + " " + lines[1]
        
        # Join the remaining lines back into a single string
        value = '\n'.join(lines[2:]) if len(lines) > 2 else ""
        
        # Assign to dictionary
        result_dict[key] = value

    return result_dict

def parse_details(text_dict):
    # Extended section keys with new fields
    section_keys = ["Syntax", "Description", "Parameter", "Remarks", "Return Format", "Example", 
                    "Class", "Function", "Command", "Input_Min", "Input_Max", "Input_Values", "Is_Query"]
    parsed_dict = {}

    for key, text in text_dict.items():
        sub_dict = {}
        current_section = None
        lines = text.split('\n')

        # Initialize the sub-dictionary with empty strings for each key
        for section in section_keys:
            sub_dict[section] = ""

        # Parse the lines into the appropriate sections
        for line in lines:
            line = line.strip()
            if line in section_keys:
                current_section = line  # Set the current section to the header found
            elif current_section:
                sub_dict[current_section] += line + ' '  # Add line to the correct section, space-separated

        # Clean up the strings by removing trailing spaces and additional formatting
        for section in section_keys:
            sub_dict[section] = sub_dict[section].strip()

        parsed_dict[key] = sub_dict

    return parsed_dict

def parse_parameters(details_dict):
    for key, sub_dict in details_dict.items():
        parameter_text = sub_dict['Parameter'].strip()
        if parameter_text == "N/A":
            sub_dict['Parameter'] = {"Info": "N/A"}
        else:
            # Split by words and identify headers directly
            words = parameter_text.split()
            if len(words) < 4:
                sub_dict['Parameter'] = {"Info": "Data incomplete or malformed"}
            else:
                param_dict = {}
                # Assuming that the headers are fixed and the values follow
                headers = ["Name", "Type", "Range", "Default"]
                values = words[4:]  # Assume first four words are headers
                
                if len(values) >= 4:  # Correct amount or more
                    param_dict['Name'] = values[0]
                    param_dict['Type'] = values[1]
                    param_dict['Default'] = values[-1]
                    param_dict['Range'] = ' '.join(values[2:-1])  # Everything else is 'Range'
                elif len(values) == 3:  # Handle special case if only three values
                    param_dict['Name'] = values[0]
                    param_dict['Type'] = values[1]
                    param_dict['Default'] = values[2]
                    param_dict['Range'] = "Not specified"
                else:
                    # If less than four values are found, handle case by case
                    param_dict['Name'] = values[0] if len(values) > 0 else "Not specified"
                    param_dict['Type'] = values[1] if len(values) > 1 else "Not specified"
                    param_dict['Default'] = values[2] if len(values) > 2 else "Not specified"
                    param_dict['Range'] = "Not specified"

                sub_dict['Parameter'] = param_dict

    return details_dict

def write_details_to_toml(details_dict, output_file, comment):
    # Convert the dictionary to TOML string
    toml_string = toml.dumps(details_dict)
    
    # Write to a file with UTF-8 encoding, including the comment at the top
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(comment + toml_string)

def generate_comment_from_filename(filename):
    # Remove file extension and replace underscores or other separators with spaces
    base_name = os.path.splitext(filename)[0]
    comment = base_name.replace('_', ':').replace('-', ' ')
    return "# " + comment + "\n"

def main():
    result = input('Do you want to overwrite the existing TOML files? (y/n): ')
    if result.lower() != 'y':
        return
    input_directory = ".\\src\\Rigol\\DHO924S\\Config\\Split PDFs"
    output_directory = ".\\src\\Rigol\\DHO924S\\Config\\Toml Config"
    
    # Ensure output directory exists
    os.makedirs(output_directory, exist_ok=True)
    
    # Process each PDF in the input directory
    for filename in os.listdir(input_directory):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(input_directory, filename)
            output_file = os.path.join(output_directory, filename.replace('.pdf', '.toml'))
            
            # Generate a comment from the filename
            comment = generate_comment_from_filename(filename)
            
            headers = extract_headers_from_pdf_by_filename(pdf_path)  # Extract headers
            
            text = []
            try:
                for k in range(0, len(headers)):
                    text.append(extract_text_by_header(pdf_path, headers[k], headers[k+1]))
            except IndexError:
                text.append(extract_text_by_header(pdf_path, headers[k]))  # Process the last header
            
            cleaned_text = remove_footer(text)
            text_dict = list_to_dict(cleaned_text)
            details = parse_details(text_dict)
            details = parse_parameters(details)
            write_details_to_toml(details, output_file, comment)  # Include the generated comment
            print(f"Processed: {filename}")
    print("All PDFs processed successfully.")

if __name__ == "__main__":
    main()






