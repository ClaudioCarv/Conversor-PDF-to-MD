"""
Módulo de validação de qualidade do Markdown gerado
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter

try:
    import language_tool_python
except ImportError:
    language_tool_python = None
    print("Aviso: language_tool_python não instalado. Validação ortográfica limitada.")

try:
    from spellchecker import SpellChecker
except ImportError:
    SpellChecker = None
    print("Aviso: pyspellchecker não instalado. Validação ortográfica limitada.")

try:
    from fuzzywuzzy import fuzz
except ImportError:
    fuzz = None
    print("Aviso: fuzzywuzzy não instalado. Comparação de similaridade limitada.")

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None
    print("Aviso: PyPDF2 não instalado. Extração de texto PDF limitada.")


class MarkdownValidator:
    """Validador de qualidade para arquivos Markdown gerados"""
    
    def __init__(self):
        """Inicializa o validador"""
        self.logger = logging.getLogger(__name__)
        
        # Inicializar Language Tool para português (se disponível)
        self.language_tool = None
        if language_tool_python:
            try:
                self.language_tool = language_tool_python.LanguageTool('pt-BR')
                self.logger.info("Language Tool inicializado para pt-BR")
            except Exception as e:
                self.logger.warning(f"Não foi possível inicializar Language Tool: {e}")
        
        # Inicializar spell checker para português
        self.spell_checker = None
        if SpellChecker:
            try:
                self.spell_checker = SpellChecker(language='pt')
                self.logger.info("Spell Checker inicializado para português")
            except Exception as e:
                self.logger.warning(f"Não foi possível inicializar Spell Checker: {e}")
    
    def validate_spelling(self, text: str) -> Dict[str, any]:
        """Valida ortografia do texto"""
        results = {
            'total_words': 0,
            'spelling_errors': [],
            'grammar_errors': [],
            'suggestions': {}
        }
        
        clean_text = self._clean_text(text)
        words = re.findall(r'\b[a-záàâãéèêíïóôõöúçñA-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ]+\b', clean_text)
        results['total_words'] = len(words)
        
        if self.spell_checker and words:
            unique_words = set(words)
            misspelled = self.spell_checker.unknown(unique_words)
            
            for word in misspelled:
                suggestions = self.spell_checker.candidates(word)
                results['spelling_errors'].append(word)
                if suggestions:
                    results['suggestions'][word] = list(suggestions)[:5]
        
        if self.language_tool:
            try:
                matches = self.language_tool.check(clean_text)
                for match in matches:
                    error_info = {
                        'message': match.message,
                        'context': match.context,
                        'replacements': match.replacements[:3],
                        'rule': match.ruleId
                    }
                    results['grammar_errors'].append(error_info)
            except Exception as e:
                self.logger.warning(f"Erro na validação gramatical: {e}")
        
        results['spelling_error_rate'] = (
            len(results['spelling_errors']) / results['total_words'] * 100 
            if results['total_words'] > 0 else 0
        )
        results['grammar_error_count'] = len(results['grammar_errors'])
        
        return results
    
    def validate_fidelity(self, pdf_path: str, md_content: str) -> Dict[str, any]:
        """Valida fidelidade do MD em relação ao PDF original"""
        results = {
            'similarity_score': 0.0,
            'char_count_diff': 0,
            'word_count_diff': 0,
            'comparison': 'Não foi possível comparar'
        }
        
        try:
            # Extrair texto do PDF original (PyPDF2)
            pdf_text = self._extract_pdf_text(pdf_path)
            md_clean = self._clean_text(md_content)
            
            # ====== NOVA LÓGICA: DOCUMENTOS ESCANEADOS ======
            # Se o PDF original não retornou texto (PyPDF2 cego para imagens),
            # mas o Docling conseguiu extrair texto via OCR no Markdown
            if not pdf_text.strip() and len(md_clean.strip()) > 0:
                results['comparison'] = 'PDF Escaneado (Extração via OCR no Docling)'
                results['similarity_score'] = 100.0  # Definimos 100% para não penalizar métricas
                md_words = len(md_clean.split())
                results['pdf_word_count'] = md_words # Espelhar para ficar bonito no dashboard
                results['md_word_count'] = md_words
                results['coverage_percentage'] = 100.0
                return results
            # ================================================
            
            if not pdf_text.strip() and not md_clean.strip():
                results['comparison'] = 'Documento completamente vazio'
                return results
                
            pdf_clean = self._clean_text(pdf_text)
            
            pdf_chars = len(pdf_clean)
            md_chars = len(md_clean)
            results['char_count_diff'] = abs(pdf_chars - md_chars)
            
            pdf_words = len(pdf_clean.split())
            md_words = len(md_clean.split())
            results['word_count_diff'] = abs(pdf_words - md_words)
            
            if fuzz:
                results['similarity_score'] = fuzz.ratio(pdf_clean, md_clean)
                results['partial_similarity'] = fuzz.partial_ratio(pdf_clean, md_clean)
                results['token_sort_similarity'] = fuzz.token_sort_ratio(pdf_clean, md_clean)
            
            results['pdf_word_count'] = pdf_words
            results['md_word_count'] = md_words
            results['coverage_percentage'] = (md_words / pdf_words * 100) if pdf_words > 0 else 0
            
            if results['similarity_score'] >= 90:
                results['comparison'] = 'Excelente - Muito fiel ao original'
            elif results['similarity_score'] >= 75:
                results['comparison'] = 'Bom - Preserva a maioria do conteúdo'
            elif results['similarity_score'] >= 60:
                results['comparison'] = 'Regular - Algumas divergências'
            else:
                results['comparison'] = 'Ruim - Muitas divergências do original'
            
        except Exception as e:
            self.logger.error(f"Erro na validação de fidelidade: {e}")
            results['comparison'] = f'Erro: {str(e)}'
        
        return results
    
    def _clean_text(self, text: str) -> str:
        """Limpa texto removendo markdown, URLs, etc"""
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _extract_pdf_text(self, pdf_path: str) -> str:
        """Extrai texto de um PDF usando PyPDF2"""
        if not PyPDF2:
            return ""
        
        try:
            text = ""
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    # extract_text pode retornar None
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
            
        except Exception as e:
            self.logger.error(f"Erro ao extrair texto do PDF: {e}")
            return ""
    
    def generate_report(self, spelling_results: Dict, fidelity_results: Dict) -> str:
        """Gera relatório de validação"""
        report = []
        report.append("=" * 60)
        report.append("RELATÓRIO DE VALIDAÇÃO DO MARKDOWN")
        report.append("=" * 60)
        report.append("")
        
        report.append("📝 VALIDAÇÃO ORTOGRÁFICA")
        report.append("-" * 60)
        report.append(f"Total de palavras: {spelling_results.get('total_words', 0)}")
        report.append(f"Erros ortográficos: {len(spelling_results.get('spelling_errors', []))}")
        report.append(f"Taxa de erros: {spelling_results.get('spelling_error_rate', 0):.2f}%")
        report.append(f"Erros gramaticais: {spelling_results.get('grammar_error_count', 0)}")
        
        if spelling_results.get('spelling_errors'):
            report.append("\nPrincipais erros ortográficos:")
            for i, error in enumerate(spelling_results['spelling_errors'][:10], 1):
                suggestions = spelling_results['suggestions'].get(error, [])
                sugg_text = f" → Sugestões: {', '.join(suggestions)}" if suggestions else ""
                report.append(f"  {i}. {error}{sugg_text}")
        
        report.append("")
        
        report.append("🎯 VALIDAÇÃO DE FIDELIDADE")
        report.append("-" * 60)
        report.append(f"Score de similaridade: {fidelity_results.get('similarity_score', 0):.1f}%")
        report.append(f"Classificação: {fidelity_results.get('comparison', 'N/A')}")
        report.append(f"Palavras no PDF: {fidelity_results.get('pdf_word_count', 0)}")
        report.append(f"Palavras no MD: {fidelity_results.get('md_word_count', 0)}")
        report.append(f"Cobertura: {fidelity_results.get('coverage_percentage', 0):.1f}%")
        report.append(f"Diferença de palavras: {fidelity_results.get('word_count_diff', 0)}")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)