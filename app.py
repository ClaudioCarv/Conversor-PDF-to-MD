import streamlit as st
import tempfile
import os

# Configura todos os caminhos de cache para a pasta /tmp (única com permissão de escrita)
os.environ["RAPIDOCR_MODEL_PATH"] = "/tmp/rapidocr_models"
os.environ['HF_HOME'] = '/tmp/huggingface'
os.environ['TORCH_HOME'] = '/tmp/torch'
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"

from pathlib import Path
import zipfile
import io
from datetime import datetime
import json


from converter import PDFToMarkdownConverter
from validator import MarkdownValidator


st.set_page_config(
    page_title="PDF para Markdown - SIAGOV",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
    .upload-text {
        font-size: 1.2rem;
        color: #1f77b4;
        font-weight: bold;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    </style>
""", unsafe_allow_html=True)


def initialize_session_state():
    if 'processed_files' not in st.session_state:
        st.session_state.processed_files = []
    if 'conversion_history' not in st.session_state:
        st.session_state.conversion_history = []


def create_temp_dirs():
    #Cria diretórios temporários para processamento
    temp_dir = tempfile.mkdtemp()
    input_dir = Path(temp_dir) / "input"
    output_dir = Path(temp_dir) / "output"
    logs_dir = Path(temp_dir) / "logs"
    
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    logs_dir.mkdir(exist_ok=True)
    
    return temp_dir, input_dir, output_dir, logs_dir


def process_pdf(pdf_file, enable_validation, converter, validator, output_dir):
    try:
        # Salvar arquivo temporário
        temp_pdf = output_dir.parent / "input" / pdf_file.name
        with open(temp_pdf, 'wb') as f:
            f.write(pdf_file.getbuffer())
        
        # Converter
        result = converter.convert_pdf_to_md(temp_pdf)
        
        if not result or not result.get('success'):
            return {
                'success': False,
                'filename': pdf_file.name,
                'error': result.get('error', 'Erro desconhecido') if result else 'Falha na conversão'
            }
        
        # Validar (se habilitado)
        if enable_validation and validator:
            spelling_results = validator.validate_spelling(result['md_content'])
            fidelity_results = validator.validate_fidelity(
                str(temp_pdf),
                result['md_content']
            )
            
            result['spelling_validation'] = spelling_results
            result['fidelity_validation'] = fidelity_results
            
            # Gerar relatório
            report = validator.generate_report(spelling_results, fidelity_results)
            result['validation_report'] = report
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'filename': pdf_file.name,
            'error': str(e)
        }


def display_validation_metrics(result):
    """Exibe métricas de validação"""
    if 'spelling_validation' in result:
        st.subheader("📊 Métricas de Qualidade")
        
        col1, col2, col3, col4 = st.columns(4)
        
        spelling = result['spelling_validation']
        fidelity = result.get('fidelity_validation', {})
        
        with col1:
            st.metric(
                "Total de Palavras",
                f"{spelling.get('total_words', 0):,}",
                help="Número total de palavras no documento"
            )
        
        with col2:
            error_count = len(spelling.get('spelling_errors', []))
            error_rate = spelling.get('spelling_error_rate', 0)
            st.metric(
                "Erros Ortográficos",
                error_count,
                f"{error_rate:.2f}%",
                delta_color="inverse"
            )
        
        with col3:
            grammar_count = spelling.get('grammar_error_count', 0)
            st.metric(
                "Erros Gramaticais",
                grammar_count,
                help="Erros gramaticais detectados"
            )
        
        with col4:
            similarity = fidelity.get('similarity_score', 0)
            st.metric(
                "Similaridade",
                f"{similarity:.1f}%",
                help="Similaridade com o PDF original"
            )
        
        # Classificação de qualidade
        comparison = fidelity.get('comparison', 'N/A')
        if similarity >= 90:
            st.success(f"✅ {comparison}")
        elif similarity >= 75:
            st.info(f"ℹ️ {comparison}")
        elif similarity >= 60:
            st.warning(f"⚠️ {comparison}")
        else:
            st.error(f"❌ {comparison}")


def display_spelling_errors(spelling_results):
    """Exibe erros ortográficos encontrados"""
    errors = spelling_results.get('spelling_errors', [])
    suggestions = spelling_results.get('suggestions', {})
    
    if errors:
        st.subheader("🔍 Erros Ortográficos Detectados")
        
        # Mostrar apenas os primeiros 20
        display_errors = errors[:20]
        
        for i, error in enumerate(display_errors, 1):
            sugg = suggestions.get(error, [])
            if sugg:
                st.write(f"{i}. **{error}** → Sugestões: {', '.join(sugg[:5])}")
            else:
                st.write(f"{i}. **{error}**")
        
        if len(errors) > 20:
            st.info(f"... e mais {len(errors) - 20} erros. Veja o relatório completo para detalhes.")
    else:
        st.success("✅ Nenhum erro ortográfico detectado!")


def create_download_package(results, output_dir):
    """Cria pacote ZIP com todos os arquivos"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for result in results:
            if result.get('success'):
                # Adicionar arquivo MD
                md_path = result['md_path']
                if os.path.exists(md_path):
                    zip_file.write(md_path, os.path.basename(md_path))
                
                # Adicionar relatório (se existir)
                if 'validation_report' in result:
                    report_name = Path(md_path).stem + '_report.txt'
                    zip_file.writestr(report_name, result['validation_report'])
        
        # Adicionar resumo JSON
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_files': len(results),
            'successful': sum(1 for r in results if r.get('success')),
            'failed': sum(1 for r in results if not r.get('success')),
            'results_summary': [
                {
                    'filename': Path(r.get('pdf_path', '')).name if r.get('pdf_path') else r.get('filename', 'unknown'),
                    'success': r.get('success', False),
                    'error': r.get('error') if not r.get('success') else None
                }
                for r in results
            ]
        }
        zip_file.writestr('summary.json', json.dumps(summary, indent=2, ensure_ascii=False))
    
    zip_buffer.seek(0)
    return zip_buffer


def main():
    """Função principal da aplicação"""
    
    initialize_session_state()
    
    # Header
    st.title("📄 Conversor PDF para Markdown")
    st.markdown("### SIAGOV - Conversão e Validação de Documentos")
    st.markdown("---")
    
    # Sidebar - Configurações
    with st.sidebar:
        st.header("⚙️ Configurações")
        
        enable_validation = st.checkbox(
            "Validar Qualidade",
            value=True,
            help="Ativa validação ortográfica e de fidelidade"
        )
        
        if enable_validation:
            st.info("✓ Validação ortográfica\n✓ Validação gramatical\n✓ Análise de fidelidade")
        
        st.markdown("---")
        
        st.subheader("Estatísticas")
        total_processed = len(st.session_state.conversion_history)
        st.metric("Arquivos Processados", total_processed)
        
        if st.session_state.conversion_history:
            successful = sum(1 for r in st.session_state.conversion_history if r.get('success'))
            st.metric("Taxa de Sucesso", f"{(successful/total_processed*100):.1f}%")
        
        st.markdown("---")
        
        # Botão para limpar histórico
        if st.button("🗑️ Limpar Histórico", use_container_width=True):
            st.session_state.conversion_history = []
            st.session_state.processed_files = []
            st.rerun()
        
        st.markdown("---")
        
        # Informações
        with st.expander("Sobre"):
            st.markdown("""
            **Recursos:**
            - Conversão PDF → Markdown usando Docling
            - OCR para documentos escaneados
            - Detecção de tabelas
            - Validação ortográfica (PT-BR)
            - Análise de fidelidade
            - Relatórios detalhados
            
            **Versão:** 1.0  
            **Projeto:** SIAGOV
            """)
    
    # Área principal
    tab1, tab2, tab3 = st.tabs(["Upload", "Resultados", "Histórico"])
    
    with tab1:
        st.subheader("Enviar Arquivos PDF")
        
        # Upload de arquivos
        uploaded_files = st.file_uploader(
            "Selecione um ou mais arquivos PDF",
            type=['pdf'],
            accept_multiple_files=True,
            help="Você pode selecionar múltiplos arquivos PDF de uma vez"
        )
        
        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)} arquivo(s) selecionado(s)")
            
            # Mostrar lista de arquivos
            with st.expander("📁 Arquivos Selecionados"):
                for i, file in enumerate(uploaded_files, 1):
                    file_size = len(file.getvalue()) / 1024  # KB
                    st.write(f"{i}. **{file.name}** ({file_size:.1f} KB)")
            
            # Botão de processamento
            if st.button("Converter Arquivos", type="primary", use_container_width=True):
                # Criar diretórios temporários
                temp_dir, input_dir, output_dir, logs_dir = create_temp_dirs()
                
                # Inicializar conversor e validador
                converter = PDFToMarkdownConverter(
                    output_dir=str(output_dir),
                    log_dir=str(logs_dir)
                )
                
                validator = None
                if enable_validation:
                    validator = MarkdownValidator()
                
                # Processar arquivos
                results = []
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, pdf_file in enumerate(uploaded_files):
                    status_text.text(f"Processando: {pdf_file.name} ({i+1}/{len(uploaded_files)})")
                    
                    result = process_pdf(
                        pdf_file,
                        enable_validation,
                        converter,
                        validator,
                        output_dir
                    )
                    
                    results.append(result)
                    progress_bar.progress((i + 1) / len(uploaded_files))
                
                status_text.empty()
                progress_bar.empty()
                
                # Salvar resultados na sessão
                st.session_state.processed_files = results
                st.session_state.conversion_history.extend(results)
                
                # Mostrar resumo
                successful = sum(1 for r in results if r.get('success'))
                failed = len(results) - successful
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total", len(results))
                with col2:
                    st.metric("Sucesso", successful, delta="✓")
                with col3:
                    if failed > 0:
                        st.metric("Falhas", failed, delta="✗", delta_color="inverse")
                    else:
                        st.metric("Falhas", failed)
                
                if successful > 0:
                    st.success(f"✅ {successful} arquivo(s) convertido(s) com sucesso!")
                
                if failed > 0:
                    st.error(f"❌ {failed} arquivo(s) com falha")
                    with st.expander("Ver erros"):
                        for r in results:
                            if not r.get('success'):
                                st.write(f"- **{r.get('filename')}**: {r.get('error')}")
                
                st.rerun()
    
    with tab2:
        st.subheader("Resultados da Conversão")
        
        if not st.session_state.processed_files:
            st.info("Envie arquivos PDF na aba **Upload** para ver os resultados aqui")
        else:
            results = st.session_state.processed_files
            
            # Resumo geral
            successful_results = [r for r in results if r.get('success')]
            
            if successful_results:
                st.success(f"✅ {len(successful_results)} arquivo(s) convertido(s)")
                
                # Download em lote
                if len(successful_results) > 1:
                    zip_buffer = create_download_package(results, None)
                    st.download_button(
                        label="📦 Baixar Todos (ZIP)",
                        data=zip_buffer,
                        file_name=f"conversao_markdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                
                st.markdown("---")
                
                # Mostrar cada resultado
                for i, result in enumerate(successful_results, 1):
                    filename = Path(result.get('pdf_path', '')).name
                    
                    with st.expander(f"📄 {i}. {filename}", expanded=(i == 1)):
                        # Informações básicas
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.write(f"**Arquivo:** {filename}")
                            st.write(f"**Páginas:** {result.get('num_pages', 0)}")
                            st.write(f"**Data:** {datetime.fromisoformat(result['timestamp']).strftime('%d/%m/%Y %H:%M:%S')}")
                        
                        with col2:
                            # Download individual
                            md_content = result.get('md_content', '')
                            if md_content:
                                st.download_button(
                                    label="Baixar MD",
                                    data=md_content,
                                    file_name=Path(filename).stem + '.md',
                                    mime="text/markdown",
                                    key=f"download_md_{i}"
                                )
                                
                                if 'validation_report' in result:
                                    st.download_button(
                                        label="Baixar Relatório",
                                        data=result['validation_report'],
                                        file_name=Path(filename).stem + '_report.txt',
                                        mime="text/plain",
                                        key=f"download_report_{i}"
                                    )
                        
                        st.markdown("---")
                        
                        # Métricas de validação
                        if 'spelling_validation' in result:
                            display_validation_metrics(result)
                            
                            st.markdown("---")
                            
                            # Erros ortográficos
                            display_spelling_errors(result['spelling_validation'])
                        
                        # Preview do Markdown
                        if st.checkbox(f"Visualizar Markdown", key=f"preview_{i}"):
                            st.markdown("**Preview:**")
                            preview_content = md_content[:2000]
                            if len(md_content) > 2000:
                                preview_content += "\n\n... (conteúdo truncado)"
                            st.code(preview_content, language="markdown")
    
    with tab3:
        st.subheader("Histórico de Conversões")
        
        if not st.session_state.conversion_history:
            st.info("Nenhuma conversão realizada ainda")
        else:
            history = st.session_state.conversion_history
            
            # Estatísticas gerais
            col1, col2, col3, col4 = st.columns(4)
            
            total = len(history)
            successful = sum(1 for r in history if r.get('success'))
            failed = total - successful
            
            with col1:
                st.metric("Total de Conversões", total)
            with col2:
                st.metric("Sucesso", successful)
            with col3:
                st.metric("Falhas", failed)
            with col4:
                success_rate = (successful / total * 100) if total > 0 else 0
                st.metric("Taxa de Sucesso", f"{success_rate:.1f}%")
            
            st.markdown("---")
            
            # Tabela de histórico
            st.subheader("📋 Registros")
            
            for i, record in enumerate(reversed(history), 1):
                filename = Path(record.get('pdf_path', '')).name if record.get('pdf_path') else record.get('filename', 'unknown')
                status = "✅" if record.get('success') else "❌"
                timestamp = record.get('timestamp', datetime.now().isoformat())
                
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime('%d/%m/%Y %H:%M:%S')
                except:
                    time_str = timestamp
                
                col1, col2, col3 = st.columns([3, 1, 2])
                
                with col1:
                    st.write(f"{status} **{filename}**")
                with col2:
                    if record.get('success'):
                        similarity = record.get('fidelity_validation', {}).get('similarity_score', 0)
                        if similarity > 0:
                            st.write(f"Similaridade: {similarity:.1f}%")
                with col3:
                    st.write(f"🕐 {time_str}")
                
                if not record.get('success'):
                    st.caption(f"⚠️ Erro: {record.get('error', 'Desconhecido')}")
                
                st.divider()


if __name__ == '__main__':
    main()