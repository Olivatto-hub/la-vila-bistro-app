import streamlit as st
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF

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

# --- Funções de Banco de Dados ---
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

def gerar_pdf_comanda(comanda_id, mesa, total, data_fechamento, df_itens):
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho - Identidade Visual (Azul #1D528A)
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
    
    # Cabeçalho da Tabela
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(110, 10, "Produto", border=1)
    pdf.cell(20, 10, "Qtd", border=1, align="C")
    pdf.cell(30, 10, "V. Unit (R$)", border=1, align="C")
    pdf.cell(30, 10, "Subtotal (R$)", border=1, align="C", ln=1)
    
    # Linhas da Tabela
    pdf.set_font("helvetica", "", 10)
    for index, row in df_itens.iterrows():
        nome_prod = str(row["Produto"])[:50]
        pdf.cell(110, 10, nome_prod, border=1)
        pdf.cell(20, 10, str(row["Qtd"]), border=1, align="C")
        pdf.cell(30, 10, f"{row['Preço Unitário']:.2f}", border=1, align="C")
        pdf.cell(30, 10, f"{row['Subtotal']:.2f}", border=1, align="C", ln=1)
    
    # Rodapé com Total
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(160, 15, "TOTAL GERAL:", align="R")
    pdf.cell(30, 15, f"R$ {total:.2f}", align="R", ln=1)
    
    pdf.set_font("helvetica", "I", 10)
    pdf.cell(0, 20, "Obrigado por escolher o La Vila Bistro!", align="C", ln=1)
    
    return bytes(pdf.output())

# --- Interface Gráfica ---
st.title("🍽️ La Vila Bistrô")
st.markdown("---")

tab_comandas, tab_cardapio, tab_estoque, tab_caixa = st.tabs([
    "📝 Comandas", "📖 Cardápio", "📦 Estoque", "💰 Caixa"
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
                    
                    # --- NOVIDADE: Mostrar os itens já consumidos na mesa ---
                    df_itens_aberta = fetch_itens_comanda(comanda['id'])
                    if not df_itens_aberta.empty:
                        st.markdown("**Itens Consumidos:**")
                        st.dataframe(df_itens_aberta, use_container_width=True, hide_index=True)
                        st.info(f"**Total Parcial Acumulado:** R$ {comanda['total']:.2f}")
                    else:
                        st.info("Nenhum item lançado nesta mesa ainda.")
                        
                    st.divider()

                    # Formulário de Adição de Itens
                    st.markdown("**Lançar Novo Item:**")
                    produtos_df = fetch_produtos()
                    produto_selecionado = st.selectbox("Adicionar Produto", produtos_df['nome'], key=f"prod_{comanda['id']}")
                    qtd = st.number_input("Quantidade", min_value=1, step=1, key=f"qtd_{comanda['id']}")
                    
                    if st.button("Lançar Item", key=f"btn_add_{comanda['id']}"):
                        prod_info = produtos_df[produtos_df['nome'] == produto_selecionado].iloc[0]
                        
                        # Inserir item
                        supabase.table("comanda_itens").insert({
                            "comanda_id": comanda['id'],
                            "produto_id": int(prod_info['id']),
                            "quantidade": qtd,
                            "preco_unitario": float(prod_info['preco'])
                        }).execute()
                        
                        # Atualizar total da comanda e baixar estoque
                        novo_total = float(comanda['total']) + (float(prod_info['preco']) * qtd)
                        novo_estoque = int(prod_info['estoque']) - qtd
                        
                        supabase.table("comandas").update({"total": novo_total}).eq("id", comanda['id']).execute()
                        supabase.table("produtos").update({"estoque": novo_estoque}).eq("id", int(prod_info['id'])).execute()
                        st.rerun()
                    
                    st.divider()
                    if st.button("Fechar Comanda (Pagamento)", key=f"btn_fechar_{comanda['id']}"):
                        supabase.table("comandas").update({
                            "status": "Fechada", 
                            "data_fechamento": "now()"
                        }).eq("id", comanda['id']).execute()
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
            supabase.table("produtos").insert({
                "categoria": cat_nova, "nome": nome_novo, "preco": preco_novo
            }).execute()
            st.success("Produto adicionado!")
            st.rerun()

    st.subheader("Itens Cadastrados")
    st.dataframe(df_produtos[['categoria', 'nome', 'preco']], use_container_width=True)

# --- ABA 3: ESTOQUE ---
with tab_estoque:
    st.header("Controle de Estoque")
    df_estoque = fetch_produtos()
    
    col_est1, col_est2 = st.columns([2, 1])
    
    with col_est1:
        st.dataframe(df_estoque[['nome', 'estoque']], use_container_width=True)
        
    with col_est2:
        st.subheader("Atualizar Estoque")
        prod_est = st.selectbox("Selecione o Produto", df_estoque['nome'])
        novo_saldo = st.number_input("Novo Saldo Total", min_value=0, step=1)
        if st.button("Atualizar Saldo"):
            prod_id = df_estoque[df_estoque['nome'] == prod_est].iloc[0]['id']
            supabase.table("produtos").update({"estoque": novo_saldo}).eq("id", int(prod_id)).execute()
            st.success("Estoque atualizado!")
            st.rerun()

# --- ABA 4: CAIXA ---
with tab_caixa:
    st.header("Controle de Caixa")
    st.write("Visão detalhada das comandas fechadas e emissão de recibos.")
    
    res_caixa = supabase.table("comandas").select("*").eq("status", "Fechada").order("data_fechamento", desc=True).execute()
    df_caixa = pd.DataFrame(res_caixa.data)
    
    if not df_caixa.empty:
        faturamento_total = df_caixa['total'].sum()
        st.metric(label="Faturamento Total Acumulado", value=f"R$ {faturamento_total:.2f}")
        st.divider()
        
        st.subheader("Histórico de Comandas Fechadas")
        for index, row in df_caixa.iterrows():
            data_str = str(row['data_fechamento'])[:16].replace("T", " ") if row['data_fechamento'] else ""
            
            with st.expander(f"🧾 Comanda #{row['id']} - Mesa {row['mesa']} | Total: R$ {row['total']:.2f} | {data_str}"):
                
                df_itens_comanda = fetch_itens_comanda(row['id'])
                
                if not df_itens_comanda.empty:
                    st.dataframe(df_itens_comanda, use_container_width=True, hide_index=True)
                    
                    pdf_bytes = gerar_pdf_comanda(row['id'], row['mesa'], row['total'], row['data_fechamento'], df_itens_comanda)
                    
                    st.download_button(
                        label="📄 Baixar Recibo em PDF",
                        data=pdf_bytes,
                        file_name=f"LaVilaBistro_Comanda_{row['id']}.pdf",
                        mime="application/pdf",
                        key=f"pdf_btn_{row['id']}"
                    )
                else:
                    st.warning("Nenhum item registrado nesta comanda (comanda vazia).")
    else:
        st.info("Nenhuma comanda fechada até o momento.")
