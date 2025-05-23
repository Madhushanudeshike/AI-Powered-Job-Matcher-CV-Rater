import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import io
import threading
import fitz # PyMuPDF
import json # To handle JSON output from Gemini (if structured parsing is desired)
import re # For regex to extract percentage if Gemini doesn't give clean JSON

# --- Configuration ---
API_KEY = "AIzaSyA2GGwX2bP0th_2TNaUKf5MHDFNkbrBrxA" # IMPORTANT: Update your API key here
try:
    from google.generativeai import configure, GenerativeModel, GenerationConfig
    configure(api_key=API_KEY)
    # Optional: Configure generation settings for more consistent JSON output
    # generation_config = GenerationConfig(response_mime_type="application/json")
except Exception as e:
    messagebox.showerror("API Configuration Error",
                         f"Failed to configure Google Gemini API. Please check your API key and internet connection.\nError: {e}")
    exit()

# --- Common Utility Functions ---

def convert_pdf_to_images(pdf_path, dpi=200):
    """
    Converts each page of a PDF file into a PNG image byte string.
    """
    image_bytes_list = []
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
            img_data = pix.pil_tobytes(format="PNG")
            image_bytes_list.append(img_data)
        doc.close()
    except Exception as e:
        print(f"Error converting PDF {pdf_path} to images: {e}")
        messagebox.showerror("PDF Conversion Error", f"Failed to convert PDF to images: {e}")
        return []
    return image_bytes_list

def get_text_from_image_data(image_data):
    """
    Extracts all readable text from a single image using Gemini Pro Vision.
    """
    try:
        model = GenerativeModel('gemini-1.5-flash')
        prompt = "Extract all readable text from this image."
        contents = [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": image_data}}
        ]
        response = model.generate_content(contents)
        if response and response.candidates:
            text_parts = [part.text for part in response.candidates[0].content.parts if hasattr(part, 'text')]
            return "".join(text_parts)
        return ""
    except Exception as e:
        print(f"Error extracting text from image with Gemini Pro Vision: {e}")
        return ""

# --- New AI Processing Functions for Job Matching ---

def parse_job_advertisement(job_ad_text):
    """
    Parses job advertisement text to extract key requirements using Gemini Pro.
    """
    try:
        model = GenerativeModel('gemini-1.5-flash') # Text-only model for parsing
        prompt = f"""Analyze the following job advertisement and extract the key requirements, including:
        - Job Title
        - Company (if clearly stated)
        - Required Skills (list technical and soft skills)
        - Desired Skills (list additional advantageous skills)
        - Experience Level (e.g., years, entry-level, senior)
        - Educational Qualifications (e.g., degree, field)
        - Key Responsibilities (brief list)

        Present this information in a structured, concise manner, like a clear bulleted list or labeled sections.
        Focus on extracting specific, actionable requirements.

        Job Advertisement:
        {job_ad_text[:6000]} # Limit input length to avoid token limits for very long ads
        """
        response = model.generate_content(prompt)
        return response.text if response else "Could not parse job advertisement."
    except Exception as e:
        print(f"Error parsing job advertisement with Gemini Pro: {e}")
        return f"Error parsing job advertisement: {e}"

def parse_cv_skills_and_experience(cv_text):
    """
    Parses CV text to extract key skills, experience, and education using Gemini Pro.
    """
    try:
        model = GenerativeModel('gemini-1.5-flash')
        prompt = f"""Analyze the following CV and extract the candidate's:
        - Name
        - Key Skills (list technical and soft skills)
        - Professional Experience (list roles, companies, and durations/key achievements)
        - Educational Background (degrees, institutions, years)
        - Any notable projects or certifications

        Present this information in a structured, concise manner, like a clear bulleted list or labeled sections.
        Focus on extracting specific, quantifiable details where possible.

        CV Content:
        {cv_text[:6000]} # Limit input length
        """
        response = model.generate_content(prompt)
        return response.text if response else "Could not parse CV."
    except Exception as e:
        print(f"Error parsing CV with Gemini Pro: {e}")
        return f"Error parsing CV: {e}"

def rate_cv_suitability(job_requirements_parsed, cv_info_parsed):
    """
    Rates the suitability of a CV against parsed job requirements and provides a percentage.
    """
    try:
        model = GenerativeModel('gemini-1.5-flash')
        prompt = f"""You are an expert HR recommender. Compare the following job advertisement requirements with the candidate's CV information.
        
        Job Requirements:
        {job_requirements_parsed}

        Candidate CV Information:
        {cv_info_parsed}

        Provide a suitability score as a percentage (0-100%) based on how well the candidate's CV matches the job requirements.
        Also, give a brief (1-3 sentences) justification for the score, highlighting primary strengths and main gaps.

        Format your response strictly as:
        PERCENTAGE: [score]%
        JUSTIFICATION: [justification text]
        """
        response = model.generate_content(prompt)
        
        # Parse the response to extract score and justification
        text = response.text if response else ""
        score = 0
        justification = "N/A - No justification provided."
        
        score_match = re.search(r"PERCENTAGE:\s*(\d+)%", text)
        if score_match:
            try:
                score = int(score_match.group(1))
                score = max(0, min(100, score)) # Ensure score is between 0 and 100
            except ValueError:
                pass # Default score 0 if conversion fails

        justification_match = re.search(r"JUSTIFICATION:\s*(.*)", text, re.DOTALL)
        if justification_match:
            justification = justification_match.group(1).strip()
        
        return score, justification
    except Exception as e:
        print(f"Error rating CV suitability with Gemini Pro: {e}")
        return 0, f"Error rating CV: {e}"

# --- GUI Application ---
class JobMatcherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI-Powered Job Matcher & CV Rater")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)

        self.job_ad_text_raw = "" # Raw text extracted from job ad
        self.job_ad_parsed_info = "" # Parsed structured info from job ad
        self.cv_data = {} # {filename: {'text_raw': '', 'parsed_info': ''}}
        self.cv_ratings = [] # [{'filename': '', 'score': int, 'justification': ''}]

        self._configure_styles()
        self._create_widgets()

    def _configure_styles(self):
        s = ttk.Style()
        s.theme_use('clam')

        s.configure('TFrame', background='#e0e0e0')
        s.configure('TButton', font=('Helvetica', 10, 'bold'), padding=8, background='#4CAF50', foreground='white')
        s.map('TButton', background=[('active', '#45a049')])

        s.configure('TLabel', font=('Helvetica', 10), background='#e0e0e0', foreground='#333333')
        s.configure('TEntry', font=('Helvetica', 10), padding=5)
        s.configure('TText', font=('Consolas', 10), padding=5) # Monospaced font for summaries

        s.configure('Header.TLabel', font=('Helvetica', 14, 'bold'), foreground='#2c3e50')
        s.configure('SubHeader.TLabel', font=('Helvetica', 12, 'bold'), foreground='#555555')
        s.configure('Status.TLabel', font=('Helvetica', 9, 'italic'))

    def _create_widgets(self):
        # Main layout: 2 columns
        self.root.columnconfigure(0, weight=1) # Left panel for uploads
        self.root.columnconfigure(1, weight=2) # Right panel for results
        self.root.rowconfigure(0, weight=1)

        # --- Left Panel: Job Ad & CV Upload ---
        self.left_panel = ttk.Frame(self.root, padding="15", relief="groove")
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.left_panel.columnconfigure(0, weight=1)

        ttk.Label(self.left_panel, text="Job & CV Uploader", style='Header.TLabel').pack(pady=10)

        # Job Advertisement Section
        ttk.Label(self.left_panel, text="1. Upload Job Advertisement (PDF/Image):", style='SubHeader.TLabel').pack(pady=(10, 5), anchor="w")
        self.upload_job_ad_button = ttk.Button(self.left_panel, text="Upload Job Ad", command=self._upload_job_ad_file)
        self.upload_job_ad_button.pack(pady=(0, 5), fill="x")
        self.job_ad_status_label = ttk.Label(self.left_panel, text="No job ad selected.")
        self.job_ad_status_label.pack(pady=(0, 10), anchor="w")

        # Job Ad Preview Text (shows parsed info)
        self.job_ad_text_preview = tk.Text(self.left_panel, height=8, wrap=tk.WORD, bg='#f8f8f8', fg='#333333', relief="sunken", bd=1, padx=5, pady=5)
        self.job_ad_text_preview.pack(pady=(0, 10), fill="both", expand=True)
        job_ad_text_scrollbar = ttk.Scrollbar(self.left_panel, command=self.job_ad_text_preview.yview)
        job_ad_text_scrollbar.pack(side="right", fill="y", in_=self.job_ad_text_preview)
        self.job_ad_text_preview['yscrollcommand'] = job_ad_text_scrollbar.set


        # Multiple CVs Section
        ttk.Label(self.left_panel, text="2. Upload Multiple CVs (PDF/Images):", style='SubHeader.TLabel').pack(pady=(10, 5), anchor="w")
        self.upload_cvs_button = ttk.Button(self.left_panel, text="Upload CVs", command=self._upload_cv_files)
        self.upload_cvs_button.pack(pady=(0, 5), fill="x")
        self.cv_count_label = ttk.Label(self.left_panel, text="No CVs selected.")
        self.cv_count_label.pack(pady=(0, 10), anchor="w")

        # --- Match/Rate Button ---
        self.match_cvs_button = ttk.Button(self.left_panel, text="3. Find Suitable CVs & Rate Others", command=self._start_matching_thread)
        self.match_cvs_button.pack(pady=20, fill="x")
        self.match_cvs_button.config(state=tk.DISABLED) # Disabled initially

        self.status_label = ttk.Label(self.left_panel, text="Ready.", style='Status.TLabel', foreground='blue')
        self.status_label.pack(pady=(5, 0), anchor="w")

        # --- Right Panel: Results ---
        self.right_panel = ttk.Frame(self.root, padding="15", relief="groove")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.right_panel.columnconfigure(0, weight=1)
        self.right_panel.rowconfigure(2, weight=1) # The 'Other CVs' list should expand

        ttk.Label(self.right_panel, text="Matching Results", style='Header.TLabel').grid(row=0, column=0, sticky="w", pady=10)

        # Most Suitable CV
        ttk.Label(self.right_panel, text="Most Suitable CV:", style='SubHeader.TLabel').grid(row=1, column=0, sticky="w", pady=(10, 5))
        self.most_suitable_cv_text = tk.Text(self.right_panel, height=5, wrap=tk.WORD, bg='#eafaea', fg='#2c3e50', relief="sunken", bd=1, padx=5, pady=5)
        self.most_suitable_cv_text.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        # No scrollbar here, just for brief display

        # Other CVs and Ratings
        ttk.Label(self.right_panel, text="Other CVs with Suitability Ratings:", style='SubHeader.TLabel').grid(row=3, column=0, sticky="w", pady=(10, 5))
        self.other_cvs_listbox = tk.Listbox(self.right_panel, bg='#f8f8f8', fg='#333333', relief="sunken", bd=1, font=('Consolas', 9))
        self.other_cvs_listbox.grid(row=4, column=0, sticky="nsew")
        
        # Scrollbar for listbox
        self.other_cvs_listbox_scrollbar = ttk.Scrollbar(self.right_panel, orient="vertical", command=self.other_cvs_listbox.yview)
        self.other_cvs_listbox_scrollbar.grid(row=4, column=1, sticky="ns")
        self.other_cvs_listbox.config(yscrollcommand=self.other_cvs_listbox_scrollbar.set)

    def _process_document_to_text_list(self, file_paths, is_single_file=False):
        """
        Helper to convert files (PDF or images) into a list of text strings (one per page/image).
        Returns (concatenated_text_string).
        """
        all_text_pages = []

        files_to_process = file_paths if isinstance(file_paths, list) else [file_paths]

        for file_path in files_to_process:
            image_bytes_list = []
            if file_path.lower().endswith('.pdf'):
                self.status_label.config(text=f"Converting {file_path.split('/')[-1]} to images...", foreground='orange')
                self.root.update_idletasks()
                image_bytes_list = convert_pdf_to_images(file_path, dpi=200) # Standard DPI
            else:
                try:
                    with open(file_path, "rb") as f:
                        image_bytes_list.append(f.read())
                except Exception as e:
                    messagebox.showerror("File Read Error", f"Could not read file {file_path}:\n{e}")
                    return "" # Return empty string on error
            
            # Process each image byte data to extract text
            for i, img_bytes in enumerate(image_bytes_list):
                self.status_label.config(text=f"Extracting text from {'page' if file_path.lower().endswith('.pdf') else 'image'} {i+1}...", foreground='orange')
                self.root.update_idletasks()
                extracted_text = get_text_from_image_data(img_bytes)
                all_text_pages.append(extracted_text)
                
            if is_single_file: # For job ad, process only the first one
                break
        
        return "\n\n".join(all_text_pages) # Concatenate all text for full document context

    def _upload_job_ad_file(self):
        """Allows user to upload a single job advertisement (PDF/Image)."""
        file_path = filedialog.askopenfilename(
            title="Select Job Advertisement",
            filetypes=[("Document Files", "*.pdf *.png *.jpg *.jpeg")]
        )
        if file_path:
            self.job_ad_text_raw = ""
            self.job_ad_parsed_info = ""
            self.job_ad_status_label.config(text=f"Processing job ad: {file_path.split('/')[-1]}", foreground='blue')
            self.job_ad_text_preview.delete(1.0, tk.END)
            self.status_label.config(text="Processing Job Ad...", foreground='orange')
            self.root.update_idletasks()

            # Process in a thread
            process_thread = threading.Thread(target=self._run_job_ad_processing, args=(file_path,))
            process_thread.start()
        else:
            self.job_ad_status_label.config(text="No job ad selected.")
            self.job_ad_text_preview.delete(1.0, tk.END)
            self.job_ad_text_raw = ""
            self.job_ad_parsed_info = ""
            self.status_label.config(text="Ready.", foreground='blue')
            self._reset_results_area()

    def _run_job_ad_processing(self, file_path):
        """Threaded function to process job ad file."""
        full_text = self._process_document_to_text_list(file_path, is_single_file=True)

        if not full_text.strip():
            self.root.after(0, lambda: self._update_job_ad_gui_error(f"Could not extract text from {file_path.split('/')[-1]}. Check file content."))
            return
        
        self.job_ad_text_raw = full_text # Store raw text for potential future use/debugging
        self.root.after(0, lambda: self.status_label.config(text="Parsing Job Ad with AI...", foreground='orange'))
        self.root.after(0, self.root.update_idletasks)

        parsed_info = parse_job_advertisement(full_text)

        self.root.after(0, self._update_job_ad_gui_after_processing, full_text, parsed_info)

    def _update_job_ad_gui_after_processing(self, full_text, parsed_info):
        """Updates GUI after job ad processing (main thread)."""
        self.job_ad_parsed_info = parsed_info # Store parsed info for later use in matching
        self.job_ad_status_label.config(text=f"Job Ad processed: {len(full_text.splitlines())} lines extracted.", foreground='green')
        self.job_ad_text_preview.delete(1.0, tk.END)
        self.job_ad_text_preview.insert(tk.END, self.job_ad_parsed_info) # Show parsed info
        self.status_label.config(text="Job Ad ready. Upload CVs.", foreground='blue')
        self._check_and_enable_match_button()

    def _update_job_ad_gui_error(self, message):
        self.job_ad_status_label.config(text=message, foreground='red')
        self.job_ad_text_preview.delete(1.0, tk.END)
        self.job_ad_text_preview.insert(tk.END, message)
        self.status_label.config(text="Job Ad processing failed.", foreground='red')
        self._reset_results_area()
        self._check_and_enable_match_button()


    def _upload_cv_files(self):
        """Allows user to upload multiple CVs (PDF/Images)."""
        file_paths = filedialog.askopenfilenames(
            title="Select CV Files",
            filetypes=[("Document Files", "*.pdf *.png *.jpg *.jpeg")],
            multiple=True
        )
        if file_paths:
            self.cv_data = {} # Clear previous CVs
            self.cv_count_label.config(text=f"Processing {len(file_paths)} CVs...", foreground='blue')
            self.status_label.config(text="Processing CVs...", foreground='orange')
            self._reset_results_area()
            self.root.update_idletasks()

            # Process in a thread
            process_thread = threading.Thread(target=self._run_cv_processing, args=(file_paths,))
            process_thread.start()
        else:
            self.cv_count_label.config(text="No CVs selected.")
            self.cv_data = {}
            self.status_label.config(text="Ready.", foreground='blue')
            self._reset_results_area()
            self._check_and_enable_match_button()

    def _run_cv_processing(self, file_paths):
        """Threaded function to process multiple CV files."""
        new_cv_data = {}
        for i, file_path in enumerate(file_paths):
            filename = file_path.split('/')[-1]
            self.root.after(0, lambda fn=filename, idx=i: self.status_label.config(
                text=f"Processing CV: {fn} ({idx+1}/{len(file_paths)})", foreground='orange'))
            self.root.after(0, self.root.update_idletasks)

            full_text = self._process_document_to_text_list(file_path)

            if full_text.strip():
                self.root.after(0, lambda fn=filename: self.status_label.config(text=f"Parsing CV: {fn} with AI...", foreground='orange'))
                self.root.after(0, self.root.update_idletasks)
                parsed_info = parse_cv_skills_and_experience(full_text)
                new_cv_data[filename] = {'text_raw': full_text, 'parsed_info': parsed_info}
            else:
                self.root.after(0, lambda fn=filename: messagebox.showwarning("Text Extraction Failed", f"Could not extract text from CV: {fn}. Skipping."))
                new_cv_data[filename] = {'text_raw': "Could not extract text.", 'parsed_info': "No text extracted."}

        self.root.after(0, self._update_cv_gui_after_processing, new_cv_data, len(file_paths))

    def _update_cv_gui_after_processing(self, new_cv_data, total_cvs):
        """Updates GUI after CV processing (main thread)."""
        self.cv_data = new_cv_data
        self.cv_count_label.config(text=f"Processed {len(self.cv_data)} out of {total_cvs} CVs.", foreground='green')
        self.status_label.config(text="CVs ready. Click 'Find Suitable CVs'.", foreground='blue')
        self._check_and_enable_match_button()

    def _check_and_enable_match_button(self):
        """Enables the match button if both job ad and CVs are loaded."""
        if self.job_ad_parsed_info and self.cv_data:
            self.match_cvs_button.config(state=tk.NORMAL)
        else:
            self.match_cvs_button.config(state=tk.DISABLED)

    def _start_matching_thread(self):
        """Starts the CV matching and rating process in a separate thread."""
        if not self.job_ad_parsed_info:
            messagebox.showwarning("Missing Job Ad", "Please upload and process a Job Advertisement first.")
            return
        if not self.cv_data:
            messagebox.showwarning("Missing CVs", "Please upload and process CV files first.")
            return

        self.match_cvs_button.config(state=tk.DISABLED)
        self.upload_job_ad_button.config(state=tk.DISABLED)
        self.upload_cvs_button.config(state=tk.DISABLED)
        self.status_label.config(text="Matching CVs... This may take a while.", foreground='orange')
        self._reset_results_area()
        self.root.update_idletasks()

        matching_thread = threading.Thread(target=self._run_matching_and_rating)
        matching_thread.start()

    def _run_matching_and_rating(self):
        """Threaded function to perform matching and rating."""
        self.cv_ratings = []
        max_score = -1
        most_suitable_cv_info = None

        job_ad_parsed = self.job_ad_parsed_info # Use the already parsed job ad info

        for i, (filename, cv_info) in enumerate(self.cv_data.items()):
            if not cv_info['parsed_info'] or "No text extracted" in cv_info['parsed_info']:
                self.root.after(0, lambda fn=filename: print(f"Skipping {fn}: No parsed profile found."))
                self.root.after(0, lambda fn=filename: self.status_label.config(
                    text=f"Skipping {fn}: profile extraction failed.", foreground='orange'))
                self.cv_ratings.append({
                    'filename': filename,
                    'score': 0,
                    'justification': "Skipped due to failed text/profile extraction."
                })
                continue

            self.root.after(0, lambda fn=filename, idx=i: self.status_label.config(
                text=f"Rating CV: {fn} ({idx+1}/{len(self.cv_data)})", foreground='orange'))
            self.root.after(0, self.root.update_idletasks)

            score, justification = rate_cv_suitability(job_ad_parsed, cv_info['parsed_info'])
            
            current_cv_rating = {
                'filename': filename,
                'score': score,
                'justification': justification
            }
            self.cv_ratings.append(current_cv_rating)

            if score > max_score:
                max_score = score
                most_suitable_cv_info = current_cv_rating
        
        # If no CVs were processed successfully
        if not self.cv_ratings and not most_suitable_cv_info:
            self.root.after(0, self._update_results_gui, None, [])
            return

        # Sort for display in listbox (highest score first)
        self.cv_ratings.sort(key=lambda x: x['score'], reverse=True)

        self.root.after(0, self._update_results_gui, most_suitable_cv_info, self.cv_ratings)


    def _update_results_gui(self, most_suitable_cv_info, all_cv_ratings):
        """Updates the results area of the GUI (main thread)."""
        # Display Most Suitable CV
        self.most_suitable_cv_text.delete(1.0, tk.END)
        if most_suitable_cv_info:
            self.most_suitable_cv_text.insert(tk.END, f"File: {most_suitable_cv_info['filename']}\n")
            self.most_suitable_cv_text.insert(tk.END, f"Suitability: {most_suitable_cv_info['score']}%\n")
            self.most_suitable_cv_text.insert(tk.END, f"Justification: {most_suitable_cv_info['justification']}\n")
        else:
            self.most_suitable_cv_text.insert(tk.END, "No suitable CV found or error occurred during processing.")

        # Display Other CVs and Ratings
        self.other_cvs_listbox.delete(0, tk.END)
        # Filter out the most suitable one if it's already displayed above, unless it's the only one
        display_list = [c for c in all_cv_ratings if c != most_suitable_cv_info or len(all_cv_ratings) == 1]
        
        for rating in display_list:
            self.other_cvs_listbox.insert(tk.END, f"{rating['filename']} - {rating['score']}%: {rating['justification']}")

        self.status_label.config(text="Matching complete!", foreground='green')
        self._reset_button_states()

    def _reset_results_area(self):
        self.most_suitable_cv_text.delete(1.0, tk.END)
        self.most_suitable_cv_text.insert(tk.END, "Upload job ad and CVs, then click 'Find Suitable CVs'.")
        self.other_cvs_listbox.delete(0, tk.END)

    def _reset_button_states(self):
        """Re-enables buttons after processing is complete."""
        self.match_cvs_button.config(state=tk.NORMAL)
        self.upload_job_ad_button.config(state=tk.NORMAL)
        self.upload_cvs_button.config(state=tk.NORMAL)
        self._check_and_enable_match_button() # Re-check state based on loaded data


if __name__ == "__main__":
    root = tk.Tk()
    app = JobMatcherApp(root)
    app._check_and_enable_match_button() # Initial check to disable button
    root.mainloop()