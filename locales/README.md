# Traducciones

Nova usa como idioma de origen el español que ya está en el código. Cada archivo `locales/<código>.json`
asocia el texto en español con su traducción; lo que no esté en el archivo se muestra en español.

Para agregar un idioma, copiá `en.json` como `<código>.json` (por ejemplo `pt.json`), traducí los valores
y elegilo en Ajustes → Idioma. El inglés cubre la interfaz completa. `python3 tools/extraer_textos.py` lista todos los textos en
español de la interfaz (los que tienen `{}` son plantillas con un valor en el medio); lo que falte
sigue en español.
