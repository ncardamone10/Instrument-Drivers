import fitz  # Import PyMuPDF
import re

def extract_headers_from_pdf(pdf_path):
    """Extracts headers from the specified PDF file based on a predefined pattern."""
    doc = fitz.open(pdf_path)  # Open the PDF file
    headers = []  # List to hold all headers found
    
    # Regex pattern to identify the start of a header
    header_start_pattern = re.compile(r'^3\.\d+') # This works for chapeter 3, change the 3 for a different chapter
    
    for page_num in range(len(doc)):  # Iterate over each page in the PDF
        page = doc[page_num]
        text = page.get_text("text")  # Extract text from the page
        lines = text.split('\n')  # Split text into lines
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if header_start_pattern.match(line):  # Check if the line starts with "3.#"
                # Assuming the header is spread over the next two lines
                full_header = line
                if i + 1 < len(lines):
                    full_header += " " + lines[i + 1].strip()
                if i + 2 < len(lines):
                    full_header += " " + lines[i + 2].strip()
                headers.append(full_header)
                i += 2  # Skip the next two lines that are part of the current header
            i += 1

    doc.close()  # Close the document
    return headers

def filter_headers(headers):
    """Filters headers to only include the main command groups and truncates text after 'Commands'."""
    filtered_headers = []
    header_filter_pattern = re.compile(r'^(3\.\d+ [A-Z:].*? Commands)') # This works for chapeter 3, change the 3 for a different chapter
    for header in headers:
        match = header_filter_pattern.search(header)
        if match:
            filtered_headers.append(match.group(1))
    return filtered_headers

def map_headers_to_pages(pdf_path, headers):
    """Map each header to the first page number it appears on in the PDF."""
    doc = fitz.open(pdf_path)
    header_to_page = {}
    header_pattern = re.compile(r'^(3\.\d+)')

    for page_num in range(len(doc)):
        page_text = doc[page_num].get_text("text")
        for header in headers:
            # First check for the presence of the section number
            match = header_pattern.match(header)
            if match and match.group(1) in page_text:
                # Now confirm if the whole header, or at least a significant part of it, is on the page
                header_remainder = header[len(match.group(1)):]  # Get the remainder of the header
                if header_remainder.strip() in page_text:
                    header_to_page[header] = page_num + 1
                    print(f"Header '{header}' found on page {page_num + 1}")
                    break  # Once a header is found, skip to the next header

    doc.close()
    return header_to_page

def split_pdf_by_headers(pdf_path, header_to_page, output_dir):
    """Splits the PDF into sections based on the page numbers mapped from the headers."""
    doc = fitz.open(pdf_path)
    headers = list(header_to_page.items())
    output_files = []

    for i in range(len(headers)):
        start_page = header_to_page[headers[i][0]] - 1  # -1 because PyMuPDF pages start from 0
        if i < len(headers) - 1:
            end_page = header_to_page[headers[i + 1][0]] - 1  # -1 to make it exclusive
        else:
            end_page = len(doc)  # Last section goes to the end of the document

        # Define output PDF path
        output_pdf_path = f"{output_dir}{headers[i][0].replace(':', '_').replace('<n>', 'n')}.pdf"
        output_doc = fitz.open()  # Create a new PDF document

        # Add pages to the new document
        try:
            for pg in range(start_page, end_page+1):
                page = doc[pg]
                output_doc.insert_pdf(doc, from_page=pg, to_page=pg)
        except Exception as e:
            print(f"Error processing pages: {e}")
            for pg in range(start_page, end_page):
                page = doc[pg]
                output_doc.insert_pdf(doc, from_page=pg, to_page=pg)
        # Save the split document
        output_doc.save(output_pdf_path)
        output_doc.close()
        output_files.append(output_pdf_path)
        print(f"Created: {output_pdf_path}")

    doc.close()
    return output_files


def main():
    pdf_path = ".\\src\\Rigol\\DHO924S\\Config\\SCPI Commands from Programming Guide.pdf"
    output_dir = ".\\src\\Rigol\\DHO924S\\Config\\"
    headers = extract_headers_from_pdf(pdf_path)  # Extract headers using your existing function
    filtered_headers = filter_headers(headers)  # Filter headers using your existing function
    header_to_page = map_headers_to_pages(pdf_path, filtered_headers)  # Map headers to pages

    # Split the PDF based on headers
    split_pdf_by_headers(pdf_path, header_to_page, output_dir)

if __name__ == "__main__":
    main()