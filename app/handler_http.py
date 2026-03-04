import aiohttp

from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

AioHttpClientInstrumentor().instrument()


class SessionManager:
    """Classe responsável por gerencia a Sessão do aioHttp"""

    _session: aiohttp.ClientSession | None = None

    @classmethod
    def init(cls):
        cls._session: aiohttp.ClientSession | None = None

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """Método responsável por obter a conexao do aiohttp"""
        if not cls._session:
            cls._session = aiohttp.ClientSession()
        return cls._session

    @classmethod
    async def close_session(cls):
        """Método responsável por fechar a conexao do aiohttp"""
        if cls._session:
            await cls._session.close()
            cls._session = None