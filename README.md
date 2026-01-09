🧠 Como Funciona a Análise do Sniper Pro

O sistema utiliza uma arquitetura de Inteligência Híbrida para encontrar valor (+EV) no mercado de apostas desportivas, com gestão automática de capital.

O Fluxo de Decisão (Pipeline)

graph TD
    A[Utilizador Seleciona o Jogo] --> B{Início da Análise};
    
    subgraph "Camada 1: Coleta de Dados (Paralelo)"
        B --> C[📊 Stats Service];
        B --> D[📰 News Service];
        B --> E[💰 Odds Service];
        
        C -->|Busca OGol/FBRef| C1[Médias de Gols Recentes];
        D -->|Busca Google/GE| D1[Notícias de Escalação e Lesões];
        E -->|API Externa| E1[Odds Atuais da Casa];
    end

    subgraph "Camada 2: Processamento"
        C1 --> F[🧮 Math Engine];
        F -->|Cálculo Poisson| F1[Probabilidade Estatística Pura];
        
        D1 --> G[🤖 AI Service];
        F1 -.-> G;
        G -->|Analisa Contexto| G1[Delta de Ajuste IA];
        G -->|Analisa Risco| G2[Tendência de Gols/BTTS];
    end

    subgraph "Camada 3: Decisão (O Sniper)"
        F1 & G1 --> H[Cálculo da Probabilidade Real];
        H --> I[Comparação com Odds (EV)];
        I --> J{Existe Valor?};
        
        J -->|Sim (+EV)| K[✅ Sugestão de Aposta (Critério de Kelly)];
        J -->|Não (-EV)| L[🚫 Alerta: Sem Valor / Não Apostar];
    end

    subgraph "Camada 4: Execução & Controle"
        K --> M[💾 Registrar Aposta];
        M --> N[📉 Atualização de Banca];
        N -->|Green| O[Soma Lucro];
        N -->|Red| P[Subtrai Stake];
    end


Detalhe dos Componentes

1. Motor Matemático (Quantitative)

Baseado na Distribuição de Poisson. Assume que o desempenho passado recente (ataque vs defesa) prediz o futuro imediato.

Entrada: Média de Gols Feitos/Sofridos (Casa e Fora).

Saída: Probabilidade base (ex: Home 50%, Draw 30%, Away 20%).

2. Analista IA (Qualitative)

Utiliza LLM (Gemini) para interpretar dados não estruturados que a matemática ignora.

Fontes: Lê matérias de "Pré-jogo", "Provável Escalação" e "Desfalques".

Lógica:

Time Titular? Mantém ou bonifica levemente.

Time Misto/Reserva? Penaliza drasticamente (-10% a -20%).

Desfalque de Craque? Penaliza moderadamente.

Must Win (Precisa ganhar)? Bonifica a motivação.

3. Gestão de Banca & Registro (Money Management)

Não basta saber em quem apostar, é preciso saber quanto e acompanhar a evolução.

Fórmula: Critério de Kelly Fracionário para definir o valor da entrada (Stake).

Registro de Entrada: O sistema salva o valor exato apostado (R$) junto com a análise no banco de dados.

Atualização Automática (Pós-Jogo):

Win (Green): Nova Banca = Banca Atual + (Valor Entrada × (Odd - 1))

Loss (Red): Nova Banca = Banca Atual - Valor Entrada

Objetivo: Crescer a banca exponencialmente com gestão de risco e manter um histórico auditável de lucratividade.