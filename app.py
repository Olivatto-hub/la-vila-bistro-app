import streamlit as st
import pandas as pd
from supabase import create_client, Client

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
                    # Adicionar itens
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
    st.write("Visão geral das comandas fechadas.")
    
    res_caixa = supabase.table("comandas").select("*").eq("status", "Fechada").execute()
    df_caixa = pd.DataFrame(res_caixa.data)
    
    if not df_caixa.empty:
        faturamento_total = df_caixa['total'].sum()
        st.metric(label="Faturamento Total Acumulado", value=f"R$ {faturamento_total:.2f}")
        st.dataframe(df_caixa[['id', 'mesa', 'total', 'data_fechamento']], use_container_width=True)
    else:
        st.info("Nenhuma comanda fechada até o momento.")
