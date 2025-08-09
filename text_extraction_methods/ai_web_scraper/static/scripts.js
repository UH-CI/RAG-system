// Fiscal Note Viewer - Interactive Functions

document.addEventListener('DOMContentLoaded', function() {
    // Enable all tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Smooth scrolling for section navigation
    document.querySelectorAll('.dropdown-menu a.dropdown-item').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);
            
            if (targetElement) {
                window.scrollTo({
                    top: targetElement.offsetTop - 70, // Offset for fixed header if needed
                    behavior: 'smooth'
                });
            }
        });
    });
    
    // Print functionality
    const printButton = document.getElementById('print-fiscal-note');
    if (printButton) {
        printButton.addEventListener('click', function() {
            window.print();
        });
    }
    
    // Confidence score color highlighting
    const confidenceBars = document.querySelectorAll('.confidence-bar');
    confidenceBars.forEach(bar => {
        // Try to get confidence from data attribute first
        let confidence;
        if (bar.hasAttribute('data-confidence')) {
            confidence = parseFloat(bar.getAttribute('data-confidence'));
            if (confidence > 0.8) {
                bar.classList.add('bg-success');
            } else if (confidence > 0.6) {
                bar.classList.add('bg-info');
            } else if (confidence > 0.4) {
                bar.classList.add('bg-warning');
            } else {
                bar.classList.add('bg-danger');
            }
        } else {
            // Fallback to the old way
            const value = parseInt(bar.style.width);
            if (value >= 80) {
                bar.classList.add('bg-success');
            } else if (value >= 60) {
                bar.classList.add('bg-info');
            } else if (value >= 40) {
                bar.classList.add('bg-warning');
            } else {
                bar.classList.add('bg-danger');
            }
        }
    });
    
    // Search functionality
    const searchInput = document.getElementById('search-fiscal-note');
    if (searchInput) {
        searchInput.addEventListener('keyup', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            // Target content in all sections instead of tabs
            const fiscalNoteContent = document.querySelectorAll('.card-body p.card-text');
            let firstMatchFound = false;
            
            if (searchTerm.length < 3) {
                fiscalNoteContent.forEach(el => {
                    el.innerHTML = el.innerHTML.replace(/<mark class="search-highlight">(.*?)<\/mark>/g, '$1');
                });
                return;
            }
            
            fiscalNoteContent.forEach(el => {
                let content = el.innerHTML;
                // First remove any existing highlights
                content = content.replace(/<mark class="search-highlight">(.*?)<\/mark>/g, '$1');
                
                // Check if this element contains the search term
                const hasMatch = el.textContent.toLowerCase().includes(searchTerm.toLowerCase());
                
                if (hasMatch) {
                    // Create a regex that preserves case but matches case insensitive
                    const regex = new RegExp(searchTerm, 'gi');
                    content = content.replace(regex, match => `<mark class="search-highlight">${match}</mark>`);
                    
                    // Scroll to the first match only
                    if (!firstMatchFound) {
                        const sectionCard = el.closest('.card');
                        if (sectionCard) {
                            sectionCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
                            firstMatchFound = true;
                        }
                    }
                }
                
                el.innerHTML = content;
            });
        });
    }
    
    // Add export to PDF functionality (if jsPDF is included)
const exportPdfButton = document.getElementById('export-pdf');

if (exportPdfButton && typeof jsPDF !== 'undefined') {
    exportPdfButton.addEventListener('click', function () {
        const doc = new jsPDF();
        const title = document.querySelector('h2')?.textContent?.trim() || 'Untitled';

        // Helper: Decode HTML entities like &nbsp;
        function decodeHtmlEntities(str) {
            const txt = document.createElement('textarea');
            txt.innerHTML = str;
            return txt.value;
        }

        // Add title to PDF
        doc.setFontSize(18);
        doc.text(title, 20, 20);

        const sections = document.querySelectorAll('.card-header, .card-body');
        let y = 30;

        sections.forEach((section) => {
            if (section.classList.contains('card-header')) {
                // Section header
                const headerText = section.textContent.trim();
                doc.setFontSize(14);
                doc.setFont(undefined, 'bold');
                doc.text(headerText, 20, y);
                y += 10;
            } else {
                const textElement = section.querySelector('p');
                let rawText = textElement ? textElement.innerHTML : '';
                
                // Convert HTML entities like &nbsp; into actual characters
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = rawText;
                let decodedText = tempDiv.textContent || tempDiv.innerText || '';
                
                // Replace non-breaking spaces with regular spaces
                decodedText = decodedText.replace(/\u00A0/g, ' ');
                
                // Break into lines for PDF
                const lines = doc.splitTextToSize(decodedText, 170);
                

                // Add new page if needed
                if (y + lines.length * 7 > 280) {
                    doc.addPage();
                    y = 20;
                }

                doc.setFontSize(20);
                doc.setFont(undefined, 'normal');
                doc.text(lines, 20, y);
                y += lines.length * 7 + 10;
            }
        });

        doc.save('fiscal-note.pdf');
    });
}

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });
});
