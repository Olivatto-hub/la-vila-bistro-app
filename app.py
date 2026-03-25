import streamlit as st
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF
import plotly.express as px
from datetime import datetime, timedelta

# Configuração da Página
st.set_page_config(page_title="La Vila Bistrô - Sistema", page_icon="🍽️", layout="wide")

# Conexão com Supabase
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_connection()
except Exception as e:
    st.error("Erro ao conectar com o banco de dados. Verifique as credenciais no secrets.")
    st.stop()

# --- Funções de Banco de Dados e BI ---
def fetch_produtos():
    res = supabase.table("produtos").select("*").order("categoria").execute()
    return pd.DataFrame(res.data)

def fetch_comandas_abertas():
    res = supabase.table("comandas").select("*").eq("status", "Aberta").execute()
    return pd.DataFrame(res.data)

def fetch_itens_comanda(comanda_id):
    res = supabase.table("comanda_itens").select("quantidade, preco_unitario, produtos(nome)").eq("comanda_id", comanda_id).execute()
    itens_formatados = []
    for item in res.data:
        itens_formatados.append({
            "Produto": item["produtos"]["nome"],
            "Qtd": item["quantidade"],
            "Preço Unitário": float(item["preco_unitario"]),
            "Subtotal": float(item["quantidade"]) * float(item["preco_unitario"])
        })
    return pd.DataFrame(itens_formatados)

def get_consumo_preditivo():
    res_c = supabase.table("comandas").select("id, data_fechamento").eq("status", "Fechada").execute()
    df_c = pd.DataFrame(res_c.data)
    if df_c.empty: return pd.DataFrame()
    
    res_i = supabase.table("comanda_itens").select("comanda_id, quantidade, produto_id").execute()
    df_i = pd.DataFrame(res_i.data)
    if df_i.empty: return pd.DataFrame()
    
    df_merged = pd.merge(df_i, df_c, left_on='comanda_id', right_on='id')
    df_merged['data_fechamento'] = pd.to_datetime(df_merged['data_fechamento'])
    
    dias_operacao = (df_merged['data_fechamento'].max().date() - df_merged['data_fechamento'].min().date()).days
    if dias_operacao <= 0: dias_operacao = 1 
    
    vendas = df_merged.groupby('produto_id')['quantidade'].sum().reset_index()
    vendas['consumo_diario_medio'] = vendas['quantidade'] / dias_operacao
    return vendas

def gerar_pdf_comanda(comanda_id, mesa, total, data_fechamento, df_itens):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(29, 82, 138)
    pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_font("helvetica", "B", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 15, "LA VILA BISTRO", align="C", ln=1)
    pdf.set_font("helvetica", "", 12)
    data_formatada = str(data_fechamento)[:16].replace("T", " ") if data_fechamento else "Data não registrada"
    pdf.cell(0, 10, f"Comanda #{comanda_id} | Mesa {mesa} | Data: {data_formatada}", align="C", ln=1)
    pdf.set_y(50)
    pdf.set_text_color(10, 37, 64)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(110, 10, "Produto", border=1)
    pdf.cell(20, 10, "Qtd", border=1, align="C")
    pdf.cell(30, 10, "V. Unit (R$)", border=1, align="C")
    pdf.cell(30, 10, "Subtotal (R$)", border=1, align="C", ln=1)
    pdf.set_font("helvetica", "", 10)
    for index, row in df_itens.iterrows():
        pdf.cell(110, 10, str(row["Produto"])[:50], border=1)
        pdf.cell(20, 10, str(row["Qtd"]), border=1, align="C")
        pdf.cell(30, 10, f"{row['Preço Unitário']:.2f}", border=1, align="C")
        pdf.cell(30, 10, f"{row['Subtotal']:.2f}", border=1, align="C", ln=1)
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(160, 15, "TOTAL GERAL:", align="R")
    pdf.cell(30, 15, f"R$ {total:.2f}", align="R", ln=1)
    pdf.set_font("helvetica", "I", 10)
    pdf.cell(0, 20, "Obrigado por escolher o La Vila Bistro!", align="C", ln=1)
    return bytes(pdf.output())

# --- NOVA FUNÇÃO: Gerar PDF de Instruções ---
def gerar_pdf_instrucoes():
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho - Identidade Visual
    pdf.set_fill_color(29, 82, 138)
    pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_font("helvetica", "B", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 15, "LA VILA BISTRO", align="C", ln=1)
    pdf.set_font("helvetica", "", 14)
    pdf.cell(0, 10, "Manual de Operacao do Sistema", align="C", ln=1)
    
    pdf.set_y(50)
    pdf.set_text_color(10, 37, 64)
    
    # Conteúdo do Manual
    instrucoes = [
        ("1. Gestao de Comandas", "Para iniciar o atendimento, digite o numero da mesa e clique em 'Abrir Comanda'. Expanda a mesa desejada para lancar novos itens. O total e o estoque sao atualizados automaticamente. Ao finalizar, clique em 'Fechar Comanda' para enviar os dados ao Caixa."),
        ("2. Gerenciamento do Cardapio", "Utilize esta aba para cadastrar novos pratos ou bebidas. Defina a categoria, o nome (com especificacao de tamanho, se houver) e o preco. Tudo o que for cadastrado aqui aparecera automaticamente na tela de comandas."),
        ("3. Controle e Movimentacao de Estoque", "Acompanhe o saldo atual de todos os produtos. Para dar entrada em mercadorias ou registrar uma perda, selecione o produto, escolha a direcao da movimentacao (Entrada ou Saida) e digite a quantidade."),
        ("4. Inteligencia e Previsao de Ruptura (IA)", "O sistema analisa o historico de vendas para prever quando um produto vai acabar. Itens com menos de 7 dias de autonomia aparecerao destacados em vermelho. Utilize essa previsao para guiar as compras da semana."),
        ("5. Caixa e Dashboards", "Verifique o faturamento do dia, da semana e do mes. Analise a Curva ABC para descobrir quais produtos vendem mais e quais estao parados no estoque. Aqui voce tambem pode reimprimir ou baixar os recibos em PDF das comandas fechadas.")
    ]
    
    for titulo, texto in instrucoes:
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, titulo, ln=1)
        pdf.set_font("helvetica", "", 10)
        pdf.multi_cell(0, 6, texto)
        pdf.ln(3)
        
    pdf.ln(10)
    pdf.set_font("helvetica", "I", 10)
    pdf.cell(0, 10, "Documento gerado automaticamente pelo Sistema Gerencial La Vila Bistro.", align="C", ln=1)
    
    return bytes(pdf.output())

# --- Interface Gráfica ---
st.title("🍽️ La Vila Bistrô")
st.markdown("---")

# EVOLUÇÃO: Adicionada a quinta aba de ajuda
tab_comandas, tab_cardapio, tab_estoque, tab_caixa, tab_ajuda = st.tabs([
    "📝 Comandas", "📖 Cardápio", "📦 Estoque", "💰 Caixa", "❓ Ajuda e Manual"
])

# --- ABA 1: COMANDAS ---
with tab_comandas:
    st.header("Gestão de Comandas")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Nova Comanda")
        nova_mesa = st.number_input("Número da Mesa", min_value=1, step=1)
        if st.button("Abrir Comanda", type="primary"):
            supabase.table("comandas").insert({"mesa": nova_mesa}).execute()
            st.success(f"Comanda para mesa {nova_mesa} aberta com sucesso!")
            st.rerun()

    with col2:
        st.subheader("Comandas Abertas")
        df_comandas = fetch_comandas_abertas()
        
        if not df_comandas.empty:
            for index, comanda in df_comandas.iterrows():
                with st.expander(f"Mesa {comanda['mesa']} - Total Parcial: R$ {comanda['total']:.2f}"):
                    df_itens_aberta = fetch_itens_comanda(comanda['id'])
                    if not df_itens_aberta.empty:
                        st.markdown("**Itens Consumidos:**")
                        st.dataframe(df_itens_aberta, use_container_width=True, hide_index=True)
                        st.info(f"**Total Parcial Acumulado:** R$ {comanda['total']:.2f}")
                    else:
                        st.info("Nenhum item lançado nesta mesa ainda.")
                        
                    st.divider()
                    st.markdown("**Lançar Novo Item:**")
                    produtos_df = fetch_produtos()
                    produto_selecionado = st.selectbox("Adicionar Produto", produtos_df['nome'], key=f"prod_{comanda['id']}")
                    qtd = st.number_input("Quantidade", min_value=1, step=1, key=f"qtd_{comanda['id']}")
                    
                    if st.button("Lançar Item", key=f"btn_add_{comanda['id']}"):
                        prod_info = produtos_df[produtos_df['nome'] == produto_selecionado].iloc[0]
                        supabase.table("comanda_itens").insert({
                            "comanda_id": comanda['id'], "produto_id": int(prod_info['id']),
                            "quantidade": qtd, "preco_unitario": float(prod_info['preco'])
                        }).execute()
                        
                        novo_total = float(comanda['total']) + (float(prod_info['preco']) * qtd)
                        novo_estoque = int(prod_info['estoque']) - qtd
                        supabase.table("comandas").update({"total": novo_total}).eq("id", comanda['id']).execute()
                        supabase.table("produtos").update({"estoque": novo_estoque}).eq("id", int(prod_info['id'])).execute()
                        st.rerun()
                    
                    st.divider()
                    if st.button("Fechar Comanda (Pagamento)", key=f"btn_fechar_{comanda['id']}"):
                        supabase.table("comandas").update({"status": "Fechada", "data_fechamento": "now()"}).eq("id", comanda['id']).execute()
                        st.success("Comanda fechada!")
                        st.rerun()
        else:
            st.info("Nenhuma comanda aberta no momento.")

# --- ABA 2: CARDÁPIO ---
with tab_cardapio:
    st.header("Gerenciamento do Cardápio")
    df_produtos = fetch_produtos()
    
    with st.expander("➕ Adicionar Novo Produto"):
        cat_nova = st.text_input("Categoria (Ex: Sucos, Prato Feito)")
        nome_novo = st.text_input("Nome do Produto")
        preco_novo = st.number_input("Preço (R$)", min_value=0.0, step=0.1, format="%.2f")
        if st.button("Salvar Produto"):
            supabase.table("produtos").insert({"categoria": cat_nova, "nome": nome_novo, "preco": preco_novo}).execute()
            st.success("Produto adicionado!")
            st.rerun()

    st.subheader("Itens Cadastrados")
    st.dataframe(df_produtos[['categoria', 'nome', 'preco']], use_container_width=True)

# --- ABA 3: ESTOQUE E PREVISÃO ---
with tab_estoque:
    st.header("Controle de Estoque e Análise Preditiva")
    
    aba_movimentacao, aba_preditiva = st.tabs(["📦 Movimentar Estoque", "🔮 Previsão de Ruptura (IA)"])
    
    with aba_movimentacao:
        df_estoque = fetch_produtos()
        col_est1, col_est2 = st.columns([2, 1])
        with col_est1:
            st.dataframe(df_estoque[['nome', 'estoque']], use_container_width=True)
        with col_est2:
            st.subheader("Movimentar Estoque")
            prod_est = st.selectbox("Selecione o Produto", df_estoque['nome'])
            tipo_movimento = st.radio("Tipo de Movimentação", ["Entrada (Adicionar)", "Saída/Baixa (Subtrair)"], horizontal=True)
            qtd_movimento = st.number_input("Quantidade", min_value=1, step=1)
            
            if st.button("Atualizar Saldo"):
                prod_info = df_estoque[df_estoque['nome'] == prod_est].iloc[0]
                prod_id = prod_info['id']
                estoque_atual = int(prod_info['estoque'])
                
                if "Entrada" in tipo_movimento:
                    novo_saldo_calculado = estoque_atual + qtd_movimento
                else:
                    novo_saldo_calculado = estoque_atual - qtd_movimento
                    
                if novo_saldo_calculado < 0:
                    st.error(f"Erro: Tentativa de baixa de {qtd_movimento}, mas só existem {estoque_atual}.")
                else:
                    supabase.table("produtos").update({"estoque": novo_saldo_calculado}).eq("id", int(prod_id)).execute()
                    st.success("Estoque atualizado!")
                    st.rerun()

    with aba_preditiva:
        st.write("Cálculo inteligente de autonomia com base no histórico de vendas reais.")
        df_preditivo = get_consumo_preditivo()
        
        if not df_preditivo.empty:
            df_estoque_atual = fetch_produtos()
            df_analise = pd.merge(df_estoque_atual, df_preditivo, left_on='id', right_on='produto_id', how='left')
            df_analise['consumo_diario_medio'] = df_analise['consumo_diario_medio'].fillna(0)
            
            df_analise['dias_autonomia'] = df_analise.apply(
                lambda row: int(row['estoque'] / row['consumo_diario_medio']) if row['consumo_diario_medio'] > 0 else float('inf'), axis=1
            )
            
            criticos = df_analise[(df_analise['dias_autonomia'] <= 7) & (df_analise['dias_autonomia'] >= 0)].sort_values('dias_autonomia')
            if not criticos.empty:
                st.error("🚨 **Atenção: Os produtos abaixo podem acabar nos próximos 7 dias!**")
                st.dataframe(criticos[['nome', 'estoque', 'consumo_diario_medio', 'dias_autonomia']], use_container_width=True, hide_index=True)
            else:
                st.success("✅ O estoque de todos os produtos está saudável no momento.")
                
            fig_est = px.bar(df_analise[df_analise['consumo_diario_medio'] > 0], x='nome', y='dias_autonomia', 
                             title="Dias Estimados de Estoque Restante por Produto", 
                             labels={'nome': 'Produto', 'dias_autonomia': 'Dias Restantes'},
                             color='dias_autonomia', color_continuous_scale='RdYlGn')
            st.plotly_chart(fig_est, use_container_width=True)
        else:
            st.info("O sistema precisa de vendas finalizadas para calcular o consumo preditivo.")

# --- ABA 4: CAIXA E DASHBOARDS ---
with tab_caixa:
    st.header("Inteligência Financeira e Caixa")
    
    aba_dash, aba_historico = st.tabs(["📊 Dashboards de Desempenho", "🧾 Histórico de Recebimentos"])
    
    res_caixa = supabase.table("comandas").select("*").eq("status", "Fechada").order("data_fechamento", desc=True).execute()
    df_caixa = pd.DataFrame(res_caixa.data)

    with aba_dash:
        if not df_caixa.empty:
            df_caixa['data_fechamento'] = pd.to_datetime(df_caixa['data_fechamento'])
            hoje = datetime.now().date()
            
            fat_hoje = df_caixa[df_caixa['data_fechamento'].dt.date == hoje]['total'].sum()
            fat_semana = df_caixa[df_caixa['data_fechamento'].dt.isocalendar().week == hoje.isocalendar()[1]]['total'].sum()
            fat_mes = df_caixa[df_caixa['data_fechamento'].dt.month == hoje.month]['total'].sum()
            
            col_d1, col_d2, col_d3 = st.columns(3)
            col_d1.metric("Faturamento Hoje", f"R$ {fat_hoje:.2f}")
            col_d2.metric("Faturamento Semana", f"R$ {fat_semana:.2f}")
            col_d3.metric("Faturamento Mês", f"R$ {fat_mes:.2f}")
            
            st.divider()
            st.subheader("Classificação de Produtos (Curva ABC & Estoque Parado)")
            
            res_todos_itens = supabase.table("comanda_itens").select("quantidade, produtos(nome)").execute()
            df_t = pd.DataFrame(res_todos_itens.data)
            
            df_produtos_geral = fetch_produtos()
            todos_produtos = df_produtos_geral['nome'].tolist()
            
            if not df_t.empty:
                df_t['produto'] = df_t['produtos'].apply(lambda x: x['nome'] if isinstance(x, dict) else x)
                vendas_agrup = df_t.groupby('produto')['quantidade'].sum().reset_index().sort_values('quantidade', ascending=False)
                
                produtos_vendidos = vendas_agrup['produto'].tolist()
                produtos_sem_saida = [p for p in todos_produtos if p not in produtos_vendidos]
                
                fig = px.bar(vendas_agrup, x='produto', y='quantidade', title="Volume Total Vendido por Produto", color='quantidade', color_continuous_scale='Blues')
                st.plotly_chart(fig, use_container_width=True)
                
                terco = max(1, len(vendas_agrup) // 3)
                alta = vendas_agrup.head(terco)['produto'].tolist()
                baixa = vendas_agrup.tail(terco)['produto'].tolist()
                media = vendas_agrup.iloc[terco:-terco]['produto'].tolist() if len(vendas_agrup) > 2 else []
                
                st.success(f"🔥 **Mais Vendidos (Alta Saída):** {', '.join(alta)}")
                if media: st.info(f"⚖️ **Consumo Mediano:** {', '.join(media)}")
                st.warning(f"❄️ **Pouca Saída:** {', '.join(baixa)}")
                
                if produtos_sem_saida:
                    st.error(f"🚫 **Sem Saída (Zero Vendas):** {', '.join(produtos_sem_saida)}")
                else:
                    st.success("🎉 Excelente! Todos os produtos do cardápio já tiveram pelo menos uma venda registrada.")
        else:
            st.info("Nenhum dado financeiro para gerar painéis.")

    with aba_historico:
        st.write("Visão detalhada das comandas fechadas e emissão de recibos.")
        if not df_caixa.empty:
            for index, row in df_caixa.iterrows():
                data_str = str(row['data_fechamento'])[:16].replace("T", " ") if row['data_fechamento'] else ""
                
                with st.expander(f"🧾 Comanda #{row['id']} - Mesa {row['mesa']} | Total: R$ {row['total']:.2f} | {data_str}"):
                    df_itens_comanda = fetch_itens_comanda(row['id'])
                    if not df_itens_comanda.empty:
                        st.dataframe(df_itens_comanda, use_container_width=True, hide_index=True)
                        st.info(f"**Total da Comanda:** R$ {row['total']:.2f}")
                        
                        pdf_bytes = gerar_pdf_comanda(row['id'], row['mesa'], row['total'], row['data_fechamento'], df_itens_comanda)
                        st.download_button(label="📄 Baixar Recibo em PDF", data=pdf_bytes, file_name=f"LaVilaBistro_Comanda_{row['id']}.pdf", mime="application/pdf", key=f"pdf_btn_{row['id']}")
                    else:
                        st.warning("Comanda vazia.")
        else:
            st.info("Nenhuma comanda fechada até o momento.")

# --- ABA 5: AJUDA E MANUAL ---
with tab_ajuda:
    st.header("Manual e Instruções de Uso")
    st.write("Bem-vindo ao sistema de gestão do La Vila Bistrô. Abaixo estão as instruções rápidas para a operação do dia a dia.")
    
    col_ajuda1, col_ajuda2 = st.columns([2, 1])
    
    with col_ajuda1:
        with st.expander("📝 1. Gestão de Comandas", expanded=True):
            st.write("Para iniciar o atendimento, digite o número da mesa e clique em **Abrir Comanda**. Expanda a mesa desejada para lançar novos itens. O total e o estoque são atualizados automaticamente. Ao finalizar, clique em **Fechar Comanda** para enviar os dados ao Caixa.")
        
        with st.expander("📖 2. Gerenciamento do Cardápio"):
            st.write("Utilize esta aba para cadastrar novos pratos ou bebidas. Defina a categoria, o nome (com especificação de tamanho, se houver) e o preço. Tudo o que for cadastrado aqui aparecerá automaticamente na tela de comandas.")
        
        with st.expander("📦 3. Controle e Movimentação de Estoque"):
            st.write("Acompanhe o saldo atual de todos os produtos. Para dar entrada em mercadorias ou registrar uma perda, selecione o produto, escolha a direção da movimentação (Entrada ou Saída) e digite a quantidade.")
            st.write("**Inteligência Preditiva:** O sistema analisa o histórico de vendas para prever quando um produto vai acabar. Itens com menos de 7 dias de autonomia aparecerão destacados em vermelho.")
            
        with st.expander("💰 4. Caixa e Dashboards"):
            st.write("Verifique o faturamento do dia, da semana e do mês. Analise a Curva ABC para descobrir quais produtos vendem mais e quais estão parados no estoque. Aqui você também pode reimprimir ou baixar os recibos em PDF das comandas fechadas.")

    with col_ajuda2:
        st.info("Você pode baixar a versão completa deste manual em PDF para imprimir ou salvar no computador do caixa.")
        
        # Gera o PDF do Manual e exibe o botão
        pdf_instrucoes_bytes = gerar_pdf_instrucoes()
        
        st.download_button(
            label="📄 Baixar Manual em PDF",
            data=pdf_instrucoes_bytes,
            file_name="LaVilaBistro_Manual.pdf",
            mime="application/pdf",
            type="primary"
        )
