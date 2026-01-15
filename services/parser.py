"""Parser service - extracts structured data from HTML/PDF documents."""
import logging
import re
import json
from typing import Dict, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from config import settings

logger = logging.getLogger(__name__)


class Parser:
    """Parser for court documents (HTML/PDF)."""
    
    def __init__(self):
        self.parser_version = settings.parser_version
        self.confidence_threshold = settings.parser_confidence_threshold
    
    def parse(self, content: bytes, content_type: str, url: str) -> Dict:
        """
        Parse document content into structured format.
        
        Args:
            content: Raw document content
            content_type: Content type (text/html, application/pdf, etc.)
            url: Source URL
            
        Returns:
            Structured document data
        """
        try:
            if 'pdf' in content_type.lower():
                return self._parse_pdf(content, url)
            else:
                return self._parse_html(content, url)
        except Exception as e:
            logger.error(f"Error parsing document from {url}: {e}", exc_info=True)
            return self._create_empty_structure(url)
    
    def _parse_html(self, content: bytes, url: str) -> Dict:
        """Parse HTML document."""
        soup = BeautifulSoup(content, 'lxml')
        
        # Extract text
        text = soup.get_text(separator='\n', strip=True)
        
        # Try to extract structured information
        # This is a placeholder - actual parsing depends on reyestr.court.gov.ua structure
        
        # Look for common patterns
        case_number = self._extract_case_number(text, soup)
        court_name = self._extract_court_name(text, soup)
        judge_name = self._extract_judge_name(text, soup)
        date = self._extract_date(text, soup)
        parties = self._extract_parties(text, soup)
        law_refs = self._extract_law_references(text, soup)
        decision = self._extract_decision(text, soup)
        amounts = self._extract_amounts(text, soup)
        
        # Split into sections
        sections = self._split_into_sections(text, soup)
        
        return {
            "doc_id": None,  # Will be set by caller
            "case_id": None,  # Will be set by caller
            "court": court_name,
            "judge": judge_name,
            "date": date,
            "case_number": case_number,
            "parties": parties,
            "claims": [],
            "law_references": law_refs,
            "decision": decision,
            "amounts": amounts,
            "appeal_possible": None,
            "text_blocks": sections,
            "source_hash": None,  # Will be set by caller
            "parser_version": self.parser_version,
            "parsed_at": datetime.utcnow().isoformat(),
            "confidence": self._calculate_confidence(court_name, judge_name, date)
        }
    
    def _parse_pdf(self, content: bytes, url: str) -> Dict:
        """Parse PDF document."""
        try:
            import PyPDF2
            from io import BytesIO
            
            pdf_file = BytesIO(content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Extract text from all pages
            text_parts = []
            for page in pdf_reader.pages:
                text_parts.append(page.extract_text())
            
            text = '\n\n'.join(text_parts)
            
            # Use similar extraction logic as HTML
            # (In production, would have more sophisticated PDF parsing)
            return self._parse_text(text, url)
            
        except ImportError:
            logger.error("PyPDF2 not installed, cannot parse PDF")
            return self._create_empty_structure(url)
        except Exception as e:
            logger.error(f"Error parsing PDF: {e}")
            return self._create_empty_structure(url)
    
    def _parse_text(self, text: str, url: str) -> Dict:
        """Parse plain text (fallback for PDF)."""
        case_number = self._extract_case_number(text, None)
        court_name = self._extract_court_name(text, None)
        judge_name = self._extract_judge_name(text, None)
        date = self._extract_date(text, None)
        parties = self._extract_parties(text, None)
        law_refs = self._extract_law_references(text, None)
        decision = self._extract_decision(text, None)
        amounts = self._extract_amounts(text, None)
        
        sections = self._split_into_sections_text(text)
        
        return {
            "doc_id": None,
            "case_id": None,
            "court": court_name,
            "judge": judge_name,
            "date": date,
            "case_number": case_number,
            "parties": parties,
            "claims": [],
            "law_references": law_refs,
            "decision": decision,
            "amounts": amounts,
            "appeal_possible": None,
            "text_blocks": sections,
            "source_hash": None,
            "parser_version": self.parser_version,
            "parsed_at": datetime.utcnow().isoformat(),
            "confidence": self._calculate_confidence(court_name, judge_name, date)
        }
    
    def _extract_case_number(self, text: str, soup: Optional[BeautifulSoup]) -> Optional[str]:
        """Extract case number from text."""
        # Pattern: справa №123/456/2024
        patterns = [
            r'справа\s*№?\s*(\d+[/-]\d+[/-]\d+)',
            r'case\s*№?\s*(\d+[/-]\d+[/-]\d+)',
            r'№\s*(\d+[/-]\d+[/-]\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def _extract_court_name(self, text: str, soup: Optional[BeautifulSoup]) -> Optional[str]:
        """Extract court name."""
        # Look for common court name patterns
        patterns = [
            r'([А-Яа-я]+ський\s+[А-Яа-я]+\s+суд)',
            r'(Суд\s+[А-Яа-я]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None
    
    def _extract_judge_name(self, text: str, soup: Optional[BeautifulSoup]) -> Optional[str]:
        """Extract judge name."""
        # Pattern: Суддя: Іванов І.І.
        patterns = [
            r'Суддя[:\s]+([А-Яа-я]+\s+[А-Я]\.[А-Я]\.)',
            r'Judge[:\s]+([А-Яа-я]+\s+[А-Я]\.[А-Я]\.)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None
    
    def _extract_date(self, text: str, soup: Optional[BeautifulSoup]) -> Optional[str]:
        """Extract document date."""
        # Pattern: DD.MM.YYYY
        patterns = [
            r'(\d{2}\.\d{2}\.\d{4})',
            r'(\d{4}-\d{2}-\d{2})',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                # Return the first date found
                return matches[0]
        return None
    
    def _extract_parties(self, text: str, soup: Optional[BeautifulSoup]) -> Dict:
        """Extract parties (plaintiff/defendant)."""
        # Placeholder - would need more sophisticated parsing
        return {
            "plaintiff": [],
            "defendant": []
        }
    
    def _extract_law_references(self, text: str, soup: Optional[BeautifulSoup]) -> List[str]:
        """Extract law article references."""
        # Pattern: ст. 625 ЦКУ, ст. 123 ККУ
        patterns = [
            r'ст\.\s*(\d+)\s+([А-Я]+)',
            r'стаття\s+(\d+)\s+([А-Я]+)',
        ]
        refs = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                refs.append(f"{match[1]} {match[0]}")
        return list(set(refs))  # Remove duplicates
    
    def _extract_decision(self, text: str, soup: Optional[BeautifulSoup]) -> Optional[str]:
        """Extract decision text."""
        # Look for "Резолютивна частина" or "DECISION"
        decision_keywords = ['резолютивна', 'рішення', 'decision', 'resolution']
        lines = text.split('\n')
        in_decision = False
        decision_lines = []
        
        for line in lines:
            if any(keyword in line.lower() for keyword in decision_keywords):
                in_decision = True
            if in_decision:
                decision_lines.append(line)
                if len(decision_lines) > 20:  # Limit decision section
                    break
        
        return '\n'.join(decision_lines) if decision_lines else None
    
    def _extract_amounts(self, text: str, soup: Optional[BeautifulSoup]) -> Dict:
        """Extract monetary amounts."""
        # Pattern: 12345.67 грн
        pattern = r'(\d+[.,]?\d*)\s*(грн|UAH|USD|EUR)'
        matches = re.findall(pattern, text)
        return {
            "amounts": [{"value": float(m[0].replace(',', '.')), "currency": m[1]} for m in matches]
        }
    
    def _split_into_sections(self, text: str, soup: Optional[BeautifulSoup]) -> List[Dict]:
        """Split document into semantic sections."""
        sections = []
        section_types = ['FACTS', 'CLAIMS', 'ARGUMENTS', 'LAW_REFERENCES', 'COURT_REASONING', 'DECISION']
        
        # Simple splitting by keywords
        lines = text.split('\n')
        current_section = None
        current_text = []
        
        for line in lines:
            # Check if line starts a new section
            for section_type in section_types:
                if section_type.lower().replace('_', ' ') in line.lower():
                    if current_section:
                        sections.append({
                            "type": current_section,
                            "text": '\n'.join(current_text)
                        })
                    current_section = section_type
                    current_text = [line]
                    break
            else:
                if current_section:
                    current_text.append(line)
        
        # Add last section
        if current_section:
            sections.append({
                "type": current_section,
                "text": '\n'.join(current_text)
            })
        
        return sections
    
    def _split_into_sections_text(self, text: str) -> List[Dict]:
        """Split plain text into sections."""
        return self._split_into_sections(text, None)
    
    def _calculate_confidence(self, court: Optional[str], judge: Optional[str], date: Optional[str]) -> float:
        """Calculate parsing confidence score."""
        score = 0.0
        if court:
            score += 0.3
        if judge:
            score += 0.3
        if date:
            score += 0.4
        return min(score, 1.0)
    
    def _create_empty_structure(self, url: str) -> Dict:
        """Create empty structure when parsing fails."""
        return {
            "doc_id": None,
            "case_id": None,
            "court": None,
            "judge": None,
            "date": None,
            "case_number": None,
            "parties": {"plaintiff": [], "defendant": []},
            "claims": [],
            "law_references": [],
            "decision": None,
            "amounts": {},
            "appeal_possible": None,
            "text_blocks": [],
            "source_hash": None,
            "parser_version": self.parser_version,
            "parsed_at": datetime.utcnow().isoformat(),
            "confidence": 0.0
        }
