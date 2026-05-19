# app.py - Dashboard Performance SDA - Mobile PWA
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import io

from core import (
    leggi_file_corrieri,
    aggrega_filiale,
    calcola_tariffa,
    ottieni_fasce_filiale,
)

st.set_page_config(
    page_title="SDA Performance",
    page_icon="📦",
    layout="centered",          # ← centered per mobile
    initial_sidebar_state="collapsed",  # ← sidebar chiusa di default su mobile
)

COLORI_FILIALI = ["#3b82f6","#22c55e","#a855f7","#f59e0b","#14b8a6","#ef4444","#ec4899","#f97316"]

LAYOUT_DARK = dict(
    plot_bgcolor="#181c24", paper_bgcolor="#0f1117", font_color="#f1f5f9",
    legend=dict(bgcolor="#1e2330", bordercolor="#2a3045", font=dict(size=11)),
)

# ── PWA + CSS MOBILE ─────────────────────────────────────────
st.markdown("""
<link rel="manifest" href="/app/static/manifest.json">
<meta name="theme-color" content="#f59e0b">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="SDA Perf">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">

<script>
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/app/static/sw.js')
        .then(() => console.log('SW registrato'))
        .catch(e => console.log('SW errore:', e));
}
</script>

<style>
/* ── Reset e base mobile ── */
:root {
    --bg:       #0f1117;
    --panel:    #1e2330;
    --border:   #2a3045;
    --text:     #f1f5f9;
    --text2:    #94a3b8;
    --accent:   #f59e0b;
    --green:    #22c55e;
    --purple:   #a855f7;
    --blue:     #3b82f6;
}

/* Nascondi header Streamlit su mobile */
header[data-testid="stHeader"] { display: none !important; }

/* Padding ridotto su mobile */
.block-container {
    padding: 0.5rem 0.75rem 2rem !important;
    max-width: 100% !important;
}

/* ── KPI card ── */
.kpi-box {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 10px 10px;
    text-align: center;
    margin-bottom: 8px;
}
.kpi-val {
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0;
    line-height: 1.15;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.kpi-lbl {
    font-size: 0.68rem;
    color: var(--text2);
    margin-top: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* ── KPI grid 2 colonne su mobile ── */
.kpi-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 12px;
}
.kpi-grid-3 { grid-template-columns: 1fr 1fr 1fr; }
.kpi-full   { grid-column: 1 / -1; }

/* ── Tabelle ── */
div[data-testid="stDataFrame"] {
    font-size: 0.75rem !important;
}
div[data-testid="stDataFrame"] table {
    font-size: 0.72rem !important;
}

/* ── Tabs ── */
div[data-testid="stTabs"] button {
    font-size: 0.72rem !important;
    padding: 6px 8px !important;
}

/* ── Sidebar mobile ── */
section[data-testid="stSidebar"] {
    background: #181c24;
    min-width: 280px !important;
}

/* ── Titoli ── */
h3 { font-size: 1.1rem !important; margin-bottom: 8px !important; }
h4 { font-size: 0.9rem !important; margin: 10px 0 4px !important; }

/* ── Bottoni periodo ── */
.periodo-btn > div { gap: 4px !important; }

/* ── Selectbox ── */
div[data-testid="stSelectbox"] { margin-bottom: 6px; }

/* ── Scrollbar tabelle ── */
div[data-testid="stDataFrame"] > div { overflow-x: auto; }

/* ── Download button ── */
div[data-testid="stDownloadButton"] button {
    width: 100% !important;
    margin-top: 8px;
}
</style>
""", unsafe_allow_html=True)


# ── HELPERS ──────────────────────────────────────────────────
def kpi_card(label: str, value: str, color: str = "#3b82f6", full=False):
    cls = "kpi-box kpi-full" if full else "kpi-box"
    st.markdown(
        f'<div class="{cls}">'
        f'<p class="kpi-val" style="color:{color}">{value}</p>'
        f'<p class="kpi-lbl">{label}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

def kpi_row(items: list):
    """Renderizza una griglia 2-colonne di KPI card.
    items = lista di (label, value, color)
    """
    cols = st.columns(2)
    for i, (lbl, val, col) in enumerate(items):
        with cols[i % 2]:
            kpi_card(lbl, val, col)

def fmt_eur(v: float) -> str:
    return f"€ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")

def fmt_n(v: float) -> str:
    return f"{int(v):,}".replace(",",".")

def colore_filiale(filiali: list, nome: str) -> str:
    try:    return COLORI_FILIALI[filiali.index(nome) % len(COLORI_FILIALI)]
    except: return "#3b82f6"

def layout_mobile(height=260, margin_r=0, extra=None):
    d = dict(**LAYOUT_DARK, height=height,
             margin=dict(l=0, r=margin_r, t=28, b=0),
             xaxis=dict(gridcolor="#2a3045", tickfont=dict(size=10)),
             yaxis=dict(gridcolor="#2a3045", tickfont=dict(size=10)))
    if extra:
        d.update(extra)
    return d


# ── GOOGLE DRIVE ──────────────────────────────────────────────
GDRIVE_FILE_ID = "12iiOzb1er1AaJXjILGlzyQJbeDLOurKu"
GDRIVE_URL = f"https://docs.google.com/spreadsheets/d/{GDRIVE_FILE_ID}/export?format=xlsx"

for k in ["dati", "date_da", "date_a"]:
    if k not in st.session_state:
        st.session_state[k] = None

# ── SIDEBAR ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📦 SDA Performance")
    st.markdown("---")

    uploaded = st.file_uploader("📂 Carica Excel", type=["xlsx","xls"])
    if uploaded:
        with st.spinner("Lettura..."):
            try:
                st.session_state.dati = leggi_file_corrieri(uploaded)
                st.success(f"✅ {len(st.session_state.dati)} filiali")
            except Exception as e:
                st.error(f"Errore: {e}")
    elif st.session_state.dati is None:
        with st.spinner("Carico da Drive..."):
            try:
                import requests
                r = requests.get(GDRIVE_URL, timeout=30)
                r.raise_for_status()
                st.session_state.dati = leggi_file_corrieri(io.BytesIO(r.content))
                st.success(f"✅ {len(st.session_state.dati)} filiali")
            except Exception as e:
                st.error(f"Drive: {e}")

    st.markdown("---")
    if st.session_state.dati:
        tutte_date = sorted({d for fil in st.session_state.dati.values() for d in fil})
        if tutte_date:
            st.markdown("### 📅 Periodo")
            date_da = st.date_input("Dal", value=tutte_date[0],
                                    min_value=tutte_date[0], max_value=tutte_date[-1])
            date_a  = st.date_input("Al",  value=tutte_date[-1],
                                    min_value=tutte_date[0], max_value=tutte_date[-1])
            st.session_state.date_da = date_da
            st.session_state.date_a  = date_a

            # Bottoni rapidi - 2 colonne su mobile
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("📅\nOggi", use_container_width=True):
                    st.session_state.date_da = st.session_state.date_a = tutte_date[-1]
                    st.rerun()
            with c2:
                if st.button("📅\n7gg", use_container_width=True):
                    st.session_state.date_a  = tutte_date[-1]
                    st.session_state.date_da = max(tutte_date[0], tutte_date[-1] - timedelta(days=6))
                    st.rerun()
            with c3:
                if st.button("📅\nTutto", use_container_width=True):
                    st.session_state.date_da = tutte_date[0]
                    st.session_state.date_a  = tutte_date[-1]
                    st.rerun()

if not st.session_state.dati:
    st.markdown("## 📦 Dashboard SDA")
    st.info("👈 Apri il menu laterale e carica il file Excel per iniziare.")
    st.stop()

dati    = st.session_state.dati
filiali = sorted(dati.keys())
date_da = st.session_state.date_da
date_a  = st.session_state.date_a

# ── TABS ──────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview", "🏢 Filiale", "📋 Giri", "📅 Giorno", "💶 Tariffa"
])


# ══════════════════════════════════════════════════════════════
# TAB 1 - PANORAMICA
# ══════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### 📊 Panoramica")
    riepilogo = []
    for fil in filiali:
        agg, _, _ = aggrega_filiale(dati[fil], date_da, date_a)
        if agg:
            riepilogo.append({"filiale": fil, **agg})

    if not riepilogo:
        st.warning("Nessun dato nel periodo.")
        st.stop()

    df_riep = pd.DataFrame(riepilogo)
    tot_af  = df_riep["tot_lv_af"].sum()
    tot_ok  = df_riep["tot_lv_ok"].sum()
    tot_rit = df_riep["tot_lv_rit"].sum()
    tot_giri_giorni = sum(
        sum(len(g) for d, g in dati[f].items()
            if (date_da is None or d >= date_da) and (date_a is None or d <= date_a))
        for f in filiali)
    prod_media = (tot_ok + tot_rit) / tot_giri_giorni if tot_giri_giorni > 0 else 0.0

    # KPI 2x2 + 1 full
    kpi_row([
        ("Filiali attive",    str(len(riepilogo)),     "#3b82f6"),
        ("Prod. Media",       f"{prod_media:.1f}",     "#f59e0b"),
    ])
    kpi_row([
        ("Tot LV Affidate",   fmt_n(tot_af),           "#3b82f6"),
        ("Tot LV Ok",         fmt_n(tot_ok),           "#22c55e"),
    ])
    kpi_row([
        ("Tot LV Ritiro",     fmt_n(tot_rit),          "#a855f7"),
        ("",                  "",                      "#0f1117"),
    ])

    st.markdown("---")

    # Grafico produttività per filiale
    st.markdown("#### Produttività per Filiale")
    fig = go.Figure()
    for _, row in df_riep.iterrows():
        fig.add_trace(go.Bar(
            x=[row["filiale"]], y=[round(row["media_prod"],1)],
            marker_color=colore_filiale(filiali, row["filiale"]),
            text=[f"{row['media_prod']:.1f}"], textposition="outside",
            showlegend=False,
        ))
    fig.update_layout(**layout_mobile(220, extra={
        "yaxis": dict(gridcolor="#2a3045", title="LDV/corriere/gg", tickfont=dict(size=10))
    }))
    st.plotly_chart(fig, use_container_width=True)

    # Grafico LV Ok vs Rit
    st.markdown("#### LV Ok vs Ritiro")
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(name="LV Ok",    x=df_riep["filiale"], y=df_riep["tot_lv_ok"],
                          marker_color="#22c55e"))
    fig2.add_trace(go.Bar(name="LV Rit",   x=df_riep["filiale"], y=df_riep["tot_lv_rit"],
                          marker_color="#a855f7"))
    fig2.update_layout(**layout_mobile(220, extra={"barmode":"group",
        "legend": dict(orientation="h", y=-0.25, font=dict(size=10))}))
    st.plotly_chart(fig2, use_container_width=True)

    # Tabella compatta
    st.markdown("#### Riepilogo")
    df_tab = df_riep[["filiale","n_giorni","tot_lv_ok","tot_lv_rit","media_prod"]].copy()
    df_tab.columns = ["Filiale","Gg","LV Ok","LV Rit","Prod."]
    df_tab["LV Ok"]  = df_tab["LV Ok"].apply(fmt_n)
    df_tab["LV Rit"] = df_tab["LV Rit"].apply(fmt_n)
    df_tab["Prod."]  = df_tab["Prod."].apply(lambda x: f"{x:.1f}")
    st.dataframe(df_tab, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# TAB 2 - DETTAGLIO FILIALE
# ══════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### 🏢 Dettaglio Filiale")
    fil_sel = st.selectbox("Filiale", filiali, key="sel_fil")
    agg, giornate, per_giro = aggrega_filiale(dati[fil_sel], date_da, date_a)

    if not agg:
        st.warning("Nessun dato.")
    else:
        kpi_row([
            ("Giorni Attivi",       str(agg["n_giorni"]),      "#94a3b8"),
            ("Prod. Media",         f"{agg['media_prod']:.1f}","#f59e0b"),
        ])
        kpi_row([
            ("Tot LV Affidate",     fmt_n(agg["tot_lv_af"]),   "#3b82f6"),
            ("Tot LV Ok",           fmt_n(agg["tot_lv_ok"]),   "#22c55e"),
        ])
        kpi_row([
            ("Tot LV Rit",          fmt_n(agg["tot_lv_rit"]),  "#a855f7"),
            ("Stop Ok",             fmt_n(agg["tot_stop_ok"]), "#14b8a6"),
        ])

        st.markdown("---")

        # Andamento giornaliero
        st.markdown("#### Andamento LV Ok / Rit")
        giorni_data = [{"data": d,
            "lv_ok":  sum(v["lv_ok"]  for v in giornate[d].values()),
            "lv_rit": sum(v["lv_rit"] for v in giornate[d].values())}
            for d in sorted(giornate)]
        df_g = pd.DataFrame(giorni_data)
        if not df_g.empty:
            fig_t = go.Figure()
            fig_t.add_trace(go.Scatter(x=df_g["data"], y=df_g["lv_ok"],
                name="LV Ok", line=dict(color="#22c55e", width=2),
                fill="tozeroy", fillcolor="rgba(34,197,94,0.08)",
                mode="lines+markers", marker=dict(size=4)))
            fig_t.add_trace(go.Scatter(x=df_g["data"], y=df_g["lv_rit"],
                name="LV Rit", line=dict(color="#a855f7", width=2),
                mode="lines+markers", marker=dict(size=4)))
            fig_t.update_layout(**layout_mobile(220, extra={
                "legend": dict(orientation="h", y=-0.3, font=dict(size=10))}))
            st.plotly_chart(fig_t, use_container_width=True)

        # Produttività per giro (barre orizzontali)
        if per_giro:
            st.markdown("#### Produttività per Giro")
            giri_s = sorted(per_giro.items())
            h = max(200, len(giri_s) * 26)
            fig_g = go.Figure(go.Bar(
                y=[f"G{g}" for g, _ in giri_s],
                x=[round(v["ldv_tot"],1) for _, v in giri_s],
                orientation="h",
                marker_color=colore_filiale(filiali, fil_sel),
                text=[f"{v['ldv_tot']:.0f}" for _, v in giri_s],
                textposition="outside", textfont=dict(size=10),
            ))
            fig_g.update_layout(**layout_mobile(h, margin_r=50, extra={
                "xaxis": dict(gridcolor="#2a3045", title="LDV/gg", tickfont=dict(size=9)),
                "yaxis": dict(gridcolor="#2a3045", autorange="reversed", tickfont=dict(size=10)),
            }))
            st.plotly_chart(fig_g, use_container_width=True)

            # Tabella giri compatta
            st.markdown("#### Tabella Giri")
            rows = [{"G": g, "Gg": v["n"],
                     "LV Ok": f"{v['lv_ok']:.0f}", "LV Rit": f"{v['lv_rit']:.0f}",
                     "Stop Ok": f"{v['stop_ok']:.0f}",
                     "Prod.": f"{v['ldv_tot']:.0f}"}
                    for g, v in sorted(per_giro.items())]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# TAB 3 - TUTTI I GIRI
# ══════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### 📋 Tutti i Giri")
    righe = []
    for fil in filiali:
        _, _, pg = aggrega_filiale(dati[fil], date_da, date_a)
        if pg:
            for giro, v in sorted(pg.items()):
                righe.append({"Filiale": fil, "Giro": giro, "Gg": v["n"],
                    "LV Ok": round(v["lv_ok"],1), "LV Rit": round(v["lv_rit"],1),
                    "Stop Ok": round(v["stop_ok"],1),
                    "Prod.": round(v["ldv_tot"],1)})

    if righe:
        df_t = pd.DataFrame(righe)
        fil_f = st.multiselect("Filtra filiale", filiali, default=filiali, key="f_tutti")
        df_tf = df_t[df_t["Filiale"].isin(fil_f)]

        if not df_tf.empty:
            st.markdown("#### Confronto Produttività")
            fig_c = go.Figure()
            for fil in fil_f:
                df_ff = df_tf[df_tf["Filiale"] == fil]
                fig_c.add_trace(go.Bar(name=fil,
                    x=df_ff["Giro"].astype(str), y=df_ff["Prod."],
                    marker_color=colore_filiale(filiali, fil)))
            fig_c.update_layout(**layout_mobile(250, extra={
                "barmode": "group",
                "xaxis": dict(gridcolor="#2a3045", title="Giro", tickfont=dict(size=9)),
                "yaxis": dict(gridcolor="#2a3045", tickfont=dict(size=9)),
                "legend": dict(orientation="h", y=-0.3, font=dict(size=10)),
            }))
            st.plotly_chart(fig_c, use_container_width=True)

        st.dataframe(df_tf, use_container_width=True, hide_index=True)
        csv = df_tf.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button("⬇ CSV", data=csv, file_name="giri.csv",
                           mime="text/csv", use_container_width=True)


# ══════════════════════════════════════════════════════════════
# TAB 4 - GIORNALIERO
# ══════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### 📅 Giornaliero")
    fil_g = st.selectbox("Filiale", filiali, key="fil_giorno")
    _, giornate_g, _ = aggrega_filiale(dati[fil_g], date_da, date_a)

    if not giornate_g:
        st.warning("Nessun dato nel periodo.")
    else:
        date_sel = st.selectbox("Data", sorted(giornate_g.keys(), reverse=True),
                                format_func=lambda d: d.strftime("%d/%m/%Y"))
        giri_day = giornate_g[date_sel]

        lv_af_g  = sum(v.get("lv_af",  0) for v in giri_day.values())
        lv_ok_g  = sum(v.get("lv_ok",  0) for v in giri_day.values())
        lv_rit_g = sum(v.get("lv_rit", 0) for v in giri_day.values())
        stop_ok  = sum(v.get("stop_ok",0) for v in giri_day.values())
        prod_tot = sum(v.get("ldv_tot",0) for v in giri_day.values())

        kpi_row([
            ("LV Affidate",  fmt_n(lv_af_g),  "#3b82f6"),
            ("LV Ok",        fmt_n(lv_ok_g),  "#22c55e"),
        ])
        kpi_row([
            ("LV Ritiro",    fmt_n(lv_rit_g), "#a855f7"),
            ("Stop Ok",      fmt_n(stop_ok),  "#14b8a6"),
        ])
        kpi_card("Prod. Totale Giornata (LDV)", fmt_n(prod_tot), "#f59e0b", full=True)

        st.markdown("---")

        righe_g = [{"Giro": g,
            "LV AFF": int(v.get("lv_af",0)),
            "LV OK":  int(v.get("lv_ok",0)),
            "LV RIT": int(v.get("lv_rit",0)),
            "STOP OK":  int(v.get("stop_ok",0)),
            "STOP RIT": int(v.get("stop_rit",0)),
            "Prod.":    int(v.get("ldv_tot",0))}
           for g, v in sorted(giri_day.items())]

        st.markdown("#### LV per Giro")
        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(
            y=[f"G{r['Giro']}" for r in righe_g],
            x=[r["LV OK"]  for r in righe_g],
            name="LV Ok", orientation="h", marker_color="#22c55e"))
        fig_d.add_trace(go.Bar(
            y=[f"G{r['Giro']}" for r in righe_g],
            x=[r["LV RIT"] for r in righe_g],
            name="LV Rit", orientation="h", marker_color="#a855f7"))
        fig_d.update_layout(**layout_mobile(max(200, len(righe_g)*28), extra={
            "barmode": "stack",
            "yaxis": dict(gridcolor="#2a3045", autorange="reversed", tickfont=dict(size=10)),
            "xaxis": dict(gridcolor="#2a3045", tickfont=dict(size=9)),
            "legend": dict(orientation="h", y=-0.25, font=dict(size=10)),
        }))
        st.plotly_chart(fig_d, use_container_width=True)

        st.dataframe(pd.DataFrame(righe_g), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# TAB 5 - TARIFFA
# ══════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### 💶 Tariffa")
    fil_t = st.selectbox("Filiale", filiali, key="fil_tar")
    _, giornate_t, _ = aggrega_filiale(dati[fil_t], date_da, date_a)

    if not giornate_t:
        st.warning("Nessun dato nel periodo.")
    else:
        fasce = ottieni_fasce_filiale(fil_t)

        with st.expander(f"Scaglioni {fil_t}"):
            for i, f in enumerate(fasce):
                st.write(f"Sc.{i+1}: {f['da']:,}–{f['a']:,} LDV → € {f['prezzo']:.3f}")

        righe_t, tot_v, tot_f, med_f = calcola_tariffa(giornate_t, fasce)

        kpi_row([
            ("Giorni",                 str(len(righe_t)), "#94a3b8"),
            ("Volume LDV",             fmt_n(tot_v),      "#3b82f6"),
        ])
        kpi_row([
            ("Fatturato Totale",       fmt_eur(tot_f),    "#22c55e"),
            ("Media Giornaliera",      fmt_eur(med_f),    "#a855f7"),
        ])

        st.markdown("---")

        df_t2 = pd.DataFrame(righe_t)

        st.markdown("#### Fatturato Giornaliero")
        fig_tar = go.Figure(go.Bar(
            x=df_t2["data"], y=df_t2["fatturato"],
            marker_color="#22c55e",
            text=[fmt_eur(v) for v in df_t2["fatturato"]],
            textposition="outside", textfont=dict(size=9),
        ))
        fig_tar.update_layout(**layout_mobile(220, extra={
            "xaxis": dict(gridcolor="#2a3045", tickfont=dict(size=9), tickangle=-45),
            "yaxis": dict(gridcolor="#2a3045", tickprefix="€ ", tickfont=dict(size=9)),
        }))
        st.plotly_chart(fig_tar, use_container_width=True)

        st.markdown("#### Volume LDV Giornaliero")
        fig_vol = go.Figure(go.Bar(
            x=df_t2["data"], y=df_t2["volume"],
            marker_color="#3b82f6",
            text=[fmt_n(v) for v in df_t2["volume"]],
            textposition="outside", textfont=dict(size=9),
        ))
        fig_vol.update_layout(**layout_mobile(200, extra={
            "xaxis": dict(gridcolor="#2a3045", tickfont=dict(size=9), tickangle=-45),
            "yaxis": dict(gridcolor="#2a3045", title="LDV", tickfont=dict(size=9)),
        }))
        st.plotly_chart(fig_vol, use_container_width=True)

        st.markdown("#### Dettaglio Scaglioni")
        st.dataframe(df_t2[["data","lv_ok","lv_rit","volume","fatturato"]],
                     use_container_width=True, hide_index=True)
