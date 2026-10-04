# Procurador de Anúncios — Windows

Aplicação local para acompanhar pesquisas na OLX e no Wallapop e enviar novos anúncios para um webhook do Discord. A interface corre no navegador predefinido, mas o servidor só aceita ligações do próprio computador.

> Esta pasta contém o código e as receitas de compilação. O instalador `ProcuradorAnuncios-Setup.exe` só existe depois de executar o processo de build num PC Windows com as ferramentas indicadas abaixo.

## Como a aplicação está organizada

Cada módulo tem uma responsabilidade principal. Assim, a interface pode mudar sem reescrever o monitor, e a persistência pode ser revista sem tocar nos sites.

| Caminho | Responsabilidade |
| --- | --- |
| `main.py` | Ponto de entrada: prepara o servidor local, inicia o monitor e abre o navegador. |
| `procurador/config.py` | Carrega, valida e guarda pesquisas e cache no perfil do utilizador. |
| `procurador/monitor.py` | Consulta OLX/Wallapop, aplica filtros, evita alertas duplicados e envia embeds Discord. |
| `procurador/web.py` | Rotas Flask, validação dos formulários e estado apresentado ao navegador. |
| `procurador/updater.py` | Consulta GitHub Releases e inicia o instalador quando há uma versão nova. |
| `procurador/templates/` | HTML das páginas; mantém conteúdo e estrutura fora do código Python. |
| `procurador/static/app.css` | Cores, disposição e comportamento responsivo da interface. |
| `procurador/static/app.js` | Atualização periódica do estado e interação com o painel. |
| `procurador/static/theme.js` | Alternância entre temas claro e escuro e preferência guardada no navegador. |
| `data/initial_config.json` | Preferências iniciais neutras, sem pesquisas pessoais nem webhook. |
| `installer/ProcuradorAnuncios.iss` | Definições do instalador Windows criado com Inno Setup. |
| `build_windows.ps1` | Instala dependências de build, empacota a app e compila o instalador. |
| `Testar_V1.vbs` | Lançador de pré-visualização por duplo clique para o PC de desenvolvimento. |

## Dados e privacidade

Quando instalada, a aplicação guarda definições e pesquisas em `%APPDATA%\ProcuradorAnuncios`. A pasta de instalação contém apenas o programa; atualizar ou reinstalar não apaga a configuração do utilizador.

Na primeira execução, `data/initial_config.json` fornece as pesquisas de exemplo e o histórico de anúncios já vistos. O webhook fica vazio e tem de ser configurado na interface. Não guardes nem publiques um URL de webhook em ficheiros de exemplo ou no repositório.

O modo de pré-visualização usa `.preview-data` ao lado do projeto para não misturar as definições de teste com as da aplicação instalada.

## Pré-visualizar no PC de desenvolvimento

Faz duplo clique em `Testar_V1.vbs`. Este modo precisa de Python e das bibliotecas do projeto instaladas neste PC. Abre o navegador sem apresentar uma janela de consola. O utilizador final da versão instalada não precisa de Python.

Sem webhook, o monitor não consulta os sites nem marca anúncios como vistos. Depois de configurar o Discord, as pesquisas ativas começam a ser verificadas pelo intervalo escolhido. Mantém a aplicação aberta para receber alertas.

## Criar o instalador para outros PCs

Num PC Windows de desenvolvimento:

1. Instala Python 3.11 ou superior, o launcher `py` e Inno Setup 6.
2. Abre PowerShell nesta pasta e executa `.\build_windows.ps1`.
3. O instalador fica em `dist\ProcuradorAnuncios-Setup.exe`.

O script cria um ambiente virtual de build e usa PyInstaller para juntar o interpretador, as bibliotecas, os templates e os ficheiros estáticos. O instalador do Inno Setup instala por utilizador, cria atalhos e não pede privilégios de administrador. Esta preparação é feita uma vez por versão; os utilizadores instalam com duplo clique no `.exe`.

## Publicar atualizações

Ao abrir a aplicação, o atualizador consulta em segundo plano a release estável mais recente de um repositório GitHub. Para ativá-lo, é necessário publicar as versões e configurar esse repositório durante o build:

1. Publica o projeto num repositório e cria uma release com uma tag de versão, por exemplo `v1.0.1`.
2. Anexa à release o instalador com nome `ProcuradorAnuncios-Setup.exe`.
3. Compila a aplicação. Este projeto já usa por omissão `Night3048/monitor-anuncios-olx` como canal de atualização; para outro repositório, indica-o no comando:

   ```powershell
   .\build_windows.ps1 -GitHubRepository "proprietario/repositorio"
   ```

4. Repete o processo para cada versão nova, atualizando `VERSION` antes de compilar.

Sem repositório configurado, a aplicação continua a funcionar, mas não consegue procurar atualizações. As verificações são guardadas em cache durante seis horas para reduzir pedidos ao GitHub.

## Fluxo de uma pesquisa

1. O formulário valida e normaliza nome, site, palavra-chave e filtros.
2. O monitor consulta o site e converte os resultados para o formato interno `{title, price, link}`.
3. Aplica exclusões, preço e, na OLX, o filtro opcional de distância.
4. Compara os links com `seen_links`; anúncios novos seguem para o Discord.
5. Só depois de o webhook aceitar o alerta é que o link fica marcado como visto.

Uma ronda de pesquisa corre de cada vez. O limite de frequência é um minuto; cinco minutos é o valor inicial recomendado. A geocodificação usa OpenStreetMap/Nominatim e guarda resultados em cache para não repetir pedidos.

## Convenções usadas no código

- Um módulo por responsabilidade e nomes que descrevem a ação ou os dados.
- Docstrings nos módulos e funções públicas para explicar propósito, argumentos relevantes e efeitos.
- Comentários para decisões não óbvias; comentários não repetem literalmente cada instrução.
- Caminhos feitos com `pathlib`, respostas HTTP com timeout e escrita JSON atómica.
- Validação dos formulários no servidor, mesmo quando o HTML também impõe limites.
- Interface responsiva em CSS separado; o JavaScript é apenas melhoria progressiva.
- O servidor liga-se a `127.0.0.1`, não à rede local.

## Diagnóstico e limitações

- **OLX:** a leitura depende da estrutura HTML pública. Se a OLX mudar o site ou devolver `403`, o painel mostra o erro e a extração pode precisar de atualização. Um `403` pode depender da rede usada; o acesso real deve ser confirmado no PC final.
- **Wallapop:** depende de `wallapy` e da disponibilidade do serviço. `fuzzywuzzy` está listado explicitamente porque é usado pelo cliente.
- **Discord:** é necessário criar um webhook e mantê-lo secreto. O código valida o domínio e a forma básica do URL antes de o guardar.
- **Execução contínua:** o computador tem de ficar ligado e a aplicação aberta. Os alertas chegam ao telemóvel através das notificações do Discord.
- **Windows apenas:** o ponto de entrada verifica o sistema operativo e termina se não for Windows.
