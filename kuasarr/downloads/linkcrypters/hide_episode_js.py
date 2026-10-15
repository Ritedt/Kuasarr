# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""FlareSolverr-JS-Blob fuer die hide.cx Episodenauswahl.

Der hide.cx Container ist eine Vue-App. Die oeffentliche API
``GET /containers/{id}`` liefert immer alle Links eines Containers, waehrend die
Webobergrenze nur die Links der gerade gewaehlten Episode anzeigt. Der Browser
kennt die Aufteilung, die API nicht - deshalb wird die bereits gerenderte Seite
per FlareSolverr ``executeJs`` manipuliert.

Die Konstante ``HIDE_EPISODE_SELECT_JS`` ist byte-exakt uebernommen und darf
nicht umformatiert werden: FlareSolverr fuehrt genau diesen String aus. Die
Platzhalter ``TOKEN`` und ``CONTAINER_ID`` werden zur Laufzeit durch
:func:`build_hide_episode_script` ersetzt.
"""

import json
from typing import Sequence

HIDE_EPISODE_SELECT_JS = "return (async () => {\n        const wanted = TOKEN, id = CONTAINER_ID;\n        function find(view) {\n            if (!view) return null;\n            if (view.component) {\n                if (view.component.type.name === 'ContainerLink')\n                    return view.component.proxy;\n                const found = find(view.component.subTree);\n                if (found) return found;\n            }\n            if (Array.isArray(view.children)) {\n                for (const child of view.children) {\n                    const found = find(child);\n                    if (found) return found;\n                }\n            }\n            return null;\n        }\n        for (let attempt = 0; attempt < 100; attempt++) {\n            const view = find(document.querySelector('#app')?._vnode);\n            if (view?.container && !view.loading) {\n                if (view.container.id !== id)\n                    return JSON.stringify({error: 'Hide container identity mismatch'});\n                if (!Array.isArray(view.extractedEpisodes) ||\n                    !view.extractedEpisodes.includes(wanted))\n                    return JSON.stringify({error: 'Episode not present in link container'});\n                view.selectedEpisode = wanted;\n                await new Promise(resolve => setTimeout(resolve, 50));\n                if (view.selectedEpisode !== wanted || !Array.isArray(view.items))\n                    return JSON.stringify({error: 'Hide episode selection failed'});\n                return JSON.stringify({selected: wanted, ids: view.items.map(link => link.id)});\n            }\n            await new Promise(resolve => setTimeout(resolve, 100));\n        }\n        return JSON.stringify({error: 'Hide episode selection unavailable'});\n    })();"


def build_hide_episode_script(container_id: str, selection: Sequence[int]) -> str:
    """Fill the placeholders of the JS blob for one concrete container.

    ``TOKEN`` is the hide.cx episode key (``S01E02``), ``CONTAINER_ID`` the
    container UUID. Both are injected JSON-encoded, so the script compares
    against real string values instead of bare identifiers.
    """
    season = int(selection[0])
    episode = int(selection[1])
    token = f"S{season:02d}E{episode:02d}"
    script = HIDE_EPISODE_SELECT_JS.replace('TOKEN', json.dumps(token))
    return script.replace('CONTAINER_ID', json.dumps(container_id))
