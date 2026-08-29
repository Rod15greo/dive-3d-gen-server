# Dive 3D Gen

## Guia de uso, distribuicao e auto-hospedagem

Versao 1.0 | Agosto de 2026

Este guia explica como usar o Dive 3D Gen no Unity e no Blender, como liberar
acesso ao servidor hospedado pela Dive Smart Factory e como implantar uma
instancia independente no Modal.

## 1. Visao geral

O Dive 3D Gen transforma uma imagem de referencia, ou um prompt no caso do
TRELLIS, em um arquivo GLB. O arquivo inclui a malha e materiais compativeis
com o fluxo PBR. Unity e Blender usam a mesma API HTTP; a diferenca esta apenas
na importacao do GLB dentro de cada editor.

- Servidor: [github.com/Rod15greo/dive-3d-gen-server](https://github.com/Rod15greo/dive-3d-gen-server)
- Plugin Unity: [github.com/Rod15greo/dive-3d-gen-unity](https://github.com/Rod15greo/dive-3d-gen-unity)
- Add-on Blender: [github.com/Rod15greo/dive-3d-gen-blender](https://github.com/Rod15greo/dive-3d-gen-blender)

O endpoint hospedado atualmente e:

```text
https://rodmeca150102--dive-3d-gen.modal.run
```

O endpoint nao e suficiente para gerar assets: cada usuario precisa de uma API
key valida. A key identifica o acesso e protege o orcamento de GPU do operador.

## 2. Escolher o modelo

- SF3D: usa somente imagem. E a opcao mais rapida para iteracoes.
- TRELLIS: aceita imagem, prompt ou ambos. Gera malha e textura PBR; e a melhor
  opcao quando a entrada textual e importante.
- Hunyuan3D-2: usa somente imagem. E adequado para assets com boa textura PBR.

As opcoes Fast, Balanced e High alteram steps de inferencia, simplificacao da
malha e resolucao da textura. Use Balanced como padrao. High custa mais tempo e
GPU; use-o somente depois de validar a imagem em Balanced.

## 3. Preparar uma boa imagem

- Use um unico objeto centralizado, visivel por inteiro e com fundo simples.
- Evite texto pequeno, reflexos muito fortes, transparencias e objetos cortados.
- Prefira imagens quadradas ou proximas de quadradas, com pelo menos 512 px.
- Para um objeto real, use iluminacao uniforme e contraste claro com o fundo.
- A IA reconstrui lados invisiveis. Use a imagem como referencia, nao como uma
  garantia de medidas exatas ou de todos os detalhes ocultos.

## 4. Usar o plugin Unity

Requisitos: Unity 6 ou superior e acesso a internet. O pacote instala o
glTFast automaticamente.

### Instalar

No Unity, abra Window > Package Manager. Clique em + e escolha Add package from
git URL. Informe a versao publicada:

```text
https://github.com/Rod15greo/dive-3d-gen-unity.git#v1.0.0
```

Como alternativa, baixe ou clone o repositorio e use Add package from disk para
selecionar o arquivo package.json.

### Gerar

1. Abra Tools > Dive 3D Gen.
2. Mantenha o Server URL padrao para usar o servidor hospedado, ou informe o
   endpoint da sua propria instancia.
3. Cole sua API Key.
4. Escolha modelo e qualidade.
5. Selecione uma imagem. TRELLIS tambem permite preencher Prompt (texto).
6. Clique em Gerar 3D e aguarde o polling concluir.
7. O GLB e salvo em Assets/Dive3DGen/Generated. Clique em Instanciar na cena.

SF3D e Hunyuan exigem imagem. O plugin bloqueia texto nesses modelos para evitar
requisicoes invalidas. Em projetos URP, o plugin converte o material importado
para URP/Lit preservando a textura base e parametros PBR.

## 5. Usar o add-on Blender

Requisitos: Blender 4.2 ou superior.

### Instalar

1. Baixe o asset Dive3DGen_Blender_Addon.zip na release v1.0.1 do repositorio
   Blender.
2. Abra Edit > Preferences > Add-ons.
3. Clique em Install from Disk, escolha o ZIP e habilite Dive 3D Gen.
4. No Viewport 3D, pressione N e abra a aba Dive 3D.

### Gerar

1. Preencha Server URL e API Key.
2. Escolha modelo, qualidade e imagem de referencia. TRELLIS tambem aceita
   somente texto.
3. Clique em Generate 3D.
4. Quando o job terminar, o GLB e importado automaticamente na colecao
   Dive 3D Gen.

Por padrao, o arquivo vai para //Dive3DGen/Generated relativo ao arquivo .blend.
Se o .blend ainda nao foi salvo, o add-on usa
Documents/Dive3DGen/Generated para evitar erro de permissao no disco C:.

## 6. Solicitar ou distribuir API keys

Quem opera o servidor deve criar uma key por pessoa ou integracao. Nunca publique
uma key em repositorios, cenas, arquivos .blend, capturas de tela ou materiais
publicos.

No diretorio do projeto do servidor, execute:

```powershell
python -m modal run scripts/manage_keys.py::create_key --name "cliente-exemplo"
```

Entregue a key por um canal privado. Para bloquear o acesso de uma pessoa:

```powershell
python -m modal run scripts/manage_keys.py::revoke_key --key "KEY_A_REVOGAR"
```

O endpoint em producao verifica o campo active da key. Uma key revogada nao pode
mais iniciar jobs. Crie keys separadas para poder revogar somente um usuario sem
interromper os demais.

## 7. Auto-hospedar no Modal

Use a auto-hospedagem quando quiser controlar custos, usuarios e endpoint. Voce
precisa de uma conta Modal, Python 3.10 ou superior e um token Hugging Face com
os termos dos modelos aceitos.

```powershell
git clone https://github.com/Rod15greo/dive-3d-gen-server.git
cd dive-3d-gen-server
python -m pip install -r requirements.txt
python -m modal setup
python -m modal secret create dive-3d-gen-huggingface HF_TOKEN=SEU_TOKEN_HF
python -m modal deploy main.py
```

O Modal cria uma URL publica no final do deploy. Use essa URL nos plugins e crie
uma API key antes de liberar acesso. Os pesos sao mantidos em um Modal Volume;
por isso o primeiro uso de cada modelo pode demorar mais que os seguintes.

Os nomes padrao dos recursos Modal sao dive-3d-gen, dive-3d-gen-models,
dive-3d-gen-api-keys e dive-3d-gen-huggingface. Eles sao isolados por conta
Modal. Para alterar os nomes, defina DIVE3D_APP_NAME, DIVE3D_MODEL_VOLUME,
DIVE3D_API_KEYS_DICT e DIVE3D_HF_SECRET antes do deploy.

## 8. API para integracoes proprias

Envie POST /generate como multipart/form-data e inclua o header X-API-Key.

```bash
curl -X POST "https://SEU_ENDPOINT/generate" \
  -H "X-API-Key: SUA_API_KEY" \
  -F "model=trellis" \
  -F "quality=balanced" \
  -F "image=@referencia.png"
```

A resposta inclui job_id. Consulte GET /status/{job_id} com o mesmo header ate
receber status done. A resposta final contem glb_base64, que deve ser decodificado
para bytes e salvo com a extensao .glb. Use GET /health para confirmar que o
endpoint esta ativo e listar os modelos disponiveis.

Campos aceitos:

- model: sf3d, trellis ou hunyuan.
- quality: fast, balanced ou high.
- prompt: texto opcional, suportado somente por TRELLIS.
- image: imagem opcional, obrigatoria para SF3D e Hunyuan.

## 9. Custos e operacao

O servidor usa GPU A10G no Modal. Cada geracao consome GPU e pode gerar cobranca
na conta do operador. Acompanhe os gastos no painel Modal e limite a distribuicao
de API keys conforme seu orcamento.

- SF3D tende a ser o mais rapido.
- Hunyuan geralmente leva dezenas de segundos.
- TRELLIS pode levar mais tempo porque inclui reconstrucao, conversao e bake da
  textura PBR.

O servidor reduz a zero quando nao ha trabalho. Isso evita custo de GPU ociosa,
mas uma nova geracao pode precisar iniciar um container antes de processar.

## 10. Solucao de problemas

- HTTP 403 ou API key invalida: confira a chave, a URL e se a key nao foi
  revogada.
- SF3D ou Hunyuan requer imagem: selecione uma imagem; esses modelos nao aceitam
  prompt sem imagem.
- Blender mostra acesso negado a Dive3DGen: salve o arquivo .blend ou mude
  Output Directory para Documents/Dive3DGen/Generated. A versao 1.0.1 ja faz
  isso automaticamente para arquivos nao salvos.
- Unity nao importa de imediato: espere o glTFast concluir a importacao e use
  Instanciar na cena novamente.
- Textura ou forma fraca: teste outra imagem com objeto inteiro, fundo mais
  simples e iluminacao uniforme. Tente Balanced antes de High.
- Primeira geracao muito lenta: espere o download dos pesos e a inicializacao do
  container; chamadas seguintes normalmente reutilizam os pesos persistidos.

## 11. Seguranca e licencas

O codigo dos tres repositorios e MIT. Os modelos baixados em tempo de execucao
mantem suas proprias licencas e condicoes: Stability AI, Microsoft TRELLIS e
Tencent Hunyuan3D-2. Leia e aceite os termos dos modelos antes de uso comercial.

Mantenha tokens Hugging Face apenas em Modal Secrets. Mantenha API keys fora do
GitHub. Se uma key vazar, revogue-a e crie outra imediatamente.
