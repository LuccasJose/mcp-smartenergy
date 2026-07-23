"""Entry point do servidor MCP do SmartEnergy.

    python server.py            # transporte streamable-http (default)
    python server.py --stdio    # transporte stdio (um cliente por processo)

A implementação fica em `src/smarty_energy/mcp/server.py`; aqui só garantimos
que o pacote em `src/` seja importável sem instalação, como faz o `main.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from smarty_energy.mcp.server import main

if __name__ == "__main__":
    main()
