# Montador de Grade Horária

## Visão Geral

Este projeto é uma aplicação web interativa, construída com Python e Streamlit, projetada para auxiliar professores e coordenadores na montagem de grades horárias. A ferramenta permite importar uma lista de disciplinas ofertadas (via arquivo `.csv`) e, através de um fluxo de três etapas, gerar combinações de horários válidas, sem conflitos, e otimizadas de acordo com as preferências do usuário.

O sistema se destaca pela flexibilidade, permitindo não apenas selecionar e filtrar disciplinas, mas também "fixar" matérias obrigatórias e agrupá-las em cenários de geração distintos (ex: "quero uma grade com o Grupo A de disciplinas **OU** com o Grupo B").

## Como Executar

1.  **Instale as dependências necessárias:**
    ```bash
    pip install streamlit pandas
    ```

2.  **Execute a aplicação a partir do seu terminal:**
    ```bash
    streamlit run preferencias.py
    ```

3.  **Acesse no seu navegador:**
    O Streamlit iniciará o servidor e fornecerá um link local para acesso (geralmente `http://localhost:8501`).

---

## Guia do Usuário (Manual)

O fluxo da aplicação é dividido em três etapas principais.

### **Etapa 1 — Carregar e Selecionar Disciplinas**

Nesta primeira tela, o objetivo é carregar a lista de disciplinas disponíveis e fazer uma pré-seleção de todas as que você *consideraria* lecionar.

1.  **Carregar Arquivo:** Na barra lateral esquerda, clique em "Faça o upload do arquivo..." e selecione o seu arquivo `.csv` com as ofertas de disciplinas.
2.  **Filtrar Ofertas:** Utilize os filtros na barra lateral para refinar a lista de disciplinas exibida. Você pode filtrar por nome, código, turma, curso, turno e dias da semana.
3.  **Selecionar Disciplinas:** Na tabela principal, marque o checkbox "Selecionar" para cada disciplina que você tem interesse. Nesta etapa, **não se preocupe com conflitos de horário**. Apenas selecione todas as possibilidades.
4.  **Avançar:** Quando estiver satisfeito com a pré-seleção, clique no botão **"Próxima etapa (revisar e fixar)"** para continuar.

### **Etapa 2 — Revisar e Fixar Disciplinas**

Esta etapa é dedicada à revisão da sua lista e à definição de quais disciplinas são essenciais.

1.  **Fixar Disciplinas:** Ao lado de cada disciplina selecionada, aparecerá um novo checkbox "Fixar". Marque esta opção para as disciplinas que **devem obrigatoriamente** estar presentes nas combinações geradas na etapa seguinte.
2.  **Relatório de Conflitos:** Um relatório de conflitos será exibido nesta tela, mostrando todas as sobreposições de horário existentes *dentro do seu conjunto de disciplinas selecionadas*. O relatório agora inclui a **Turma** para facilitar a identificação. Use esta informação para refinar sua seleção, se necessário, voltando à Etapa 1.
3.  **Avançar:** Após revisar e marcar as disciplinas fixas, clique em **"Confirmar e ir para agrupamento (Etapa 3)"**.

### **Etapa 3 — Agrupar Fixas e Gerar Combinações**

Esta é a etapa final, onde você define a lógica de geração e visualiza as grades horárias.

1.  **Definir Preferências Gerais:**
    *   **Número de disciplinas:** Defina o tamanho exato das grades que você deseja. Se deixar em "0", o sistema gerará combinações de tamanhos variados.
    *   **Dias totais na semana:** Restrinja as grades a um número específico de dias de trabalho.
    *   **Turnos de preferência:** Selecione os turnos que você prefere. Isso não filtra, mas aumenta o "score" (a pontuação) das combinações que os contêm, fazendo com que apareçam primeiro.

2.  **Agrupar Disciplinas Fixas:**
    *   Para cada disciplina que você marcou como "Fixa" na Etapa 2, um menu de seleção aparecerá. Você pode atribuí-la a um dos três grupos (`Grupo A`, `Grupo B`, `Grupo C`) ou deixá-la como `Sem grupo`.
    *   **Lógica de Grupos:**
        *   **Modo OR (padrão):** O sistema criará cenários separados para cada grupo. Ex: um conjunto de horários válidos para o "Grupo A" e outro para o "Grupo B".
        *   **Modo AND:** Ative o botão "Incluir grupos A/B/C juntos (AND)". Com isso, o sistema gerará apenas grades que contenham **todas as disciplinas de todos os grupos ativos** simultaneamente.
    *   **Disciplinas "Sem grupo":** Use o botão "Fixas 'Sem grupo' são obrigatórias..." para definir se as disciplinas não agrupadas devem aparecer em todos os cenários gerados.

3.  **Gerar Combinações:**
    *   Clique no botão **"Gerar combinações"**.
    *   O sistema calculará todas as grades possíveis que respeitem suas regras: sem conflitos de horário, com as disciplinas obrigatórias de cada cenário e com as preferências definidas.
    *   As melhores 4 sugestões de cada cenário aparecerão primeiro, seguidas por uma lista expansível com todas as outras opções válidas. Disciplinas que foram "Fixadas" na Etapa 2 aparecerão em **negrito**.

---

## Para Desenvolvedores

*   **Tecnologias:** O projeto é escrito em Python 3 e utiliza as bibliotecas `streamlit` para a interface web e `pandas` para a manipulação de dados.
*   **Estrutura do Código:** Toda a lógica da aplicação está contida no arquivo `preferencias.py`. As funções são comentadas para explicar seu propósito, desde o parsing de horários (`parse_horarios`) até a verificação de conflitos (`check_conflito`) e a pontuação de combinações (`score_combo`).
*   **Customização:**
    *   A constante `MAX_COMBINACOES` pode ser ajustada para controlar o limite de performance.
    *   A lógica de pontuação na função `score_combo` pode ser facilmente estendida para incluir novas regras de negócio.
    *   Novos filtros ou regras de validação podem ser adicionados seguindo a estrutura existente.

## Como Contribuir

Contribuições são bem-vindas! Sinta-se à vontade para abrir uma *issue* para relatar bugs ou sugerir novas funcionalidades. Se desejar contribuir com código, por favor, crie um *Pull Request* a partir de uma *branch* separada.
