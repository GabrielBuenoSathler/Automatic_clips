import os
import pickle
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

# Diretório raiz do projeto (onde ficam credentials.json e .env)
BASE_DIR = Path(__file__).resolve().parents[2]

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]


class YouTubeAPI:
    def __init__(self, use_oauth: bool = True):
        self.use_oauth = use_oauth
        self.youtube = None
        self.credentials = None
        self.authenticate()

    def authenticate(self):
        """Autentica com a API do YouTube usando OAuth 2.0 ou chave de API"""
        if self.use_oauth:
            self._authenticate_oauth()
        else:
            self._authenticate_api_key()

    def _authenticate_oauth(self):
        """Autentica usando OAuth 2.0 (necessário para upload)"""
        creds = None
        token_file = str(BASE_DIR / "token.pickle")

        if os.path.exists(token_file):
            with open(token_file, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                credentials_file = os.getenv("YOUTUBE_CREDENTIALS", "credentials.json")
                # Resolve caminhos relativos a partir da raiz do projeto, não do CWD
                if not os.path.isabs(credentials_file):
                    credentials_file = str(BASE_DIR / credentials_file)
                if not os.path.exists(credentials_file):
                    raise FileNotFoundError(
                        f"Arquivo '{credentials_file}' não encontrado. "
                        "Baixe as credenciais OAuth 2.0 do Google Cloud Console."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(token_file, "wb") as token:
                pickle.dump(creds, token)

        self.credentials = creds
        self.youtube = build("youtube", "v3", credentials=creds)
        print("✓ Autenticado com sucesso na API do YouTube via OAuth 2.0")

    def _authenticate_api_key(self):
        """Autentica usando chave de API (apenas leitura)"""
        api_key = os.getenv("YOUTUBE")
        if not api_key:
            raise ValueError(
                "Chave de API do YouTube não encontrada. "
                "Adicione YOUTUBE=sua_chave_api no arquivo .env"
            )

        self.youtube = build("youtube", "v3", developerKey=api_key)
        print("✓ Autenticado com sucesso na API do YouTube (chave de API)")

    def get_channel_info(self) -> dict:
        """Obtém informações do canal do usuário autenticado"""
        request = self.youtube.channels().list(
            part="snippet,statistics,contentDetails",
            mine=True
        )
        response = request.execute()

        if response["items"]:
            return response["items"][0]
        return None

    def search_videos(self, query: str, max_results: int = 10) -> list:
        """
        Busca vídeos no YouTube

        Args:
            query: Termo de busca
            max_results: Número máximo de resultados

        Returns:
            Lista com resultados da busca
        """
        request = self.youtube.search().list(
            q=query,
            part="snippet",
            maxResults=max_results,
            type="video"
        )
        response = request.execute()
        return response.get("items", [])

    def get_video_stats(self, video_id: str) -> dict:
        """Obtém estatísticas de um vídeo"""
        request = self.youtube.videos().list(
            part="statistics,snippet",
            id=video_id
        )
        response = request.execute()

        if response["items"]:
            return response["items"][0]
        return None

    def upload_video(self, file_path: str, title: str, description: str = "",
                    privacy_status: str = "private", tags: list = None) -> dict:
        """
        Faz upload de um vídeo para o YouTube

        Args:
            file_path: Caminho do arquivo de vídeo
            title: Título do vídeo
            description: Descrição do vídeo
            privacy_status: "public", "private" ou "unlisted"
            tags: Lista de tags/palavras-chave

        Returns:
            Dicionário com informações do vídeo enviado
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {file_path}")

        if not self.use_oauth:
            raise ValueError("Upload requer autenticação OAuth 2.0")

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

        request = self.youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    print(f"Upload {int(status.progress() * 100)}% concluído")
            except Exception as e:
                print(f"Erro durante o upload: {e}")
                raise

        print(f"✓ Vídeo enviado com sucesso! ID: {response['id']}")
        return response


def upload_video_interactive():
    """Interface interativa para upload de vídeo"""
    try:
        yt = YouTubeAPI(use_oauth=True)

        print("\n" + "="*50)
        print("UPLOAD DE VÍDEO PARA YOUTUBE")
        print("="*50)

        file_path = input("\nCaminho do arquivo de vídeo: ").strip()
        if not os.path.exists(file_path):
            print(f"✗ Arquivo não encontrado: {file_path}")
            return

        title = input("Título do vídeo: ").strip()
        if not title:
            print("✗ Título é obrigatório")
            return

        description = input("Descrição (opcional): ").strip()

        privacy = input("Privacidade (public/private/unlisted) [private]: ").strip() or "private"
        if privacy not in ["public", "private", "unlisted"]:
            print(f"✗ Privacidade inválida. Usando 'private'")
            privacy = "private"

        tags_input = input("Tags separadas por vírgula (opcional): ").strip()
        tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()]

        print(f"\nResumo do upload:")
        print(f"  Título: {title}")
        print(f"  Privacidade: {privacy}")
        print(f"  Tags: {', '.join(tags) if tags else 'Nenhuma'}")

        confirm = input("\nConfirmar upload? (s/n): ").strip().lower()
        if confirm != "s":
            print("Upload cancelado")
            return

        result = yt.upload_video(
            file_path=file_path,
            title=title,
            description=description,
            privacy_status=privacy,
            tags=tags
        )
        print(f"\n✓ Upload concluído com sucesso!")
        print(f"  ID do vídeo: {result['id']}")

    except FileNotFoundError as e:
        print(f"✗ Erro: {e}")
    except ValueError as e:
        print(f"✗ Erro: {e}")
    except Exception as e:
        print(f"✗ Erro ao fazer upload: {e}")


def search_videos_interactive():
    """Interface interativa para buscar vídeos"""
    try:
        yt = YouTubeAPI(use_oauth=False)

        query = input("\nTermo de busca: ").strip()
        if not query:
            print("✗ Termo de busca é obrigatório")
            return

        max_results = input("Número máximo de resultados [10]: ").strip()
        max_results = int(max_results) if max_results.isdigit() else 10

        print(f"\nBuscando vídeos sobre '{query}'...")
        videos = yt.search_videos(query, max_results=max_results)

        if not videos:
            print("✗ Nenhum vídeo encontrado")
            return

        print(f"\n✓ {len(videos)} vídeo(s) encontrado(s):\n")
        for i, video in enumerate(videos, 1):
            video_id = video["id"]["videoId"]
            title = video["snippet"]["title"]
            print(f"{i}. {title}")
            print(f"   ID: {video_id}\n")

        view_stats = input("Ver estatísticas de algum vídeo? (número ou enter para sair): ").strip()
        if view_stats.isdigit():
            idx = int(view_stats) - 1
            if 0 <= idx < len(videos):
                video_id = videos[idx]["id"]["videoId"]
                stats = yt.get_video_stats(video_id)
                if stats:
                    print(f"\n📊 Estatísticas: {stats['snippet']['title']}")
                    print(f"   Visualizações: {stats['statistics'].get('viewCount', 'N/A')}")
                    print(f"   Curtidas: {stats['statistics'].get('likeCount', 'N/A')}")
                    print(f"   Comentários: {stats['statistics'].get('commentCount', 'N/A')}")

    except ValueError as e:
        print(f"✗ Erro: {e}")
    except Exception as e:
        print(f"✗ Erro ao buscar vídeos: {e}")


def find_mp4_videos(directory: Path = BASE_DIR) -> list:
    """
    Pesquisa recursivamente todos os arquivos .mp4 em um diretório

    Args:
        directory: Diretório raiz da busca (padrão: raiz do projeto)

    Returns:
        Lista de caminhos (Path) dos arquivos .mp4 encontrados
    """
    return sorted(directory.rglob("*.mp4"))


def list_mp4_videos_interactive():
    """Interface interativa para pesquisar vídeos .mp4 e fazer upload"""
    print(f"\nPesquisando arquivos .mp4 em: {BASE_DIR}")
    videos = find_mp4_videos()

    if not videos:
        print("✗ Nenhum arquivo .mp4 encontrado")
        return

    print(f"\n✓ {len(videos)} arquivo(s) .mp4 encontrado(s):\n")
    for i, video in enumerate(videos, 1):
        size_mb = video.stat().st_size / (1024 * 1024)
        print(f"{i}. {video.relative_to(BASE_DIR)} ({size_mb:.1f} MB)")

    selection = input("\nNúmero do vídeo para postar no YouTube (enter para sair): ").strip()
    if not selection.isdigit():
        return

    idx = int(selection) - 1
    if not (0 <= idx < len(videos)):
        print("✗ Número inválido")
        return

    video_path = videos[idx]
    title = input(f"Título [{video_path.stem}]: ").strip() or video_path.stem
    description = input("Descrição (opcional): ").strip()
    privacy = input("Privacidade (public/private/unlisted) [private]: ").strip() or "private"
    if privacy not in ["public", "private", "unlisted"]:
        print("✗ Privacidade inválida. Usando 'private'")
        privacy = "private"
    tags_input = input("Tags separadas por vírgula (opcional): ").strip()
    tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()]

    print(f"\nResumo do upload:")
    print(f"  Arquivo: {video_path.relative_to(BASE_DIR)}")
    print(f"  Título: {title}")
    print(f"  Privacidade: {privacy}")
    print(f"  Tags: {', '.join(tags) if tags else 'Nenhuma'}")

    confirm = input("\nConfirmar upload? (s/n): ").strip().lower()
    if confirm != "s":
        print("Upload cancelado")
        return

    try:
        yt = YouTubeAPI(use_oauth=True)
        result = yt.upload_video(
            file_path=str(video_path),
            title=title,
            description=description,
            privacy_status=privacy,
            tags=tags
        )
        print(f"\n✓ Upload concluído com sucesso!")
        print(f"  ID do vídeo: {result['id']}")
    except Exception as e:
        print(f"✗ Erro ao fazer upload: {e}")


def main():
    """Menu principal da aplicação"""
    while True:
        print("\n" + "="*50)
        print("GERENCIADOR DE YOUTUBE")
        print("="*50)
        print("1 - Buscar vídeos e ver estatísticas")
        print("2 - Fazer upload de um vídeo")
        print("3 - Ver informações do canal")
        print("4 - Pesquisar e postar vídeo .mp4 do diretório")
        print("0 - Sair")
        print("="*50)

        choice = input("Escolha uma opção: ").strip()

        if choice == "1":
            search_videos_interactive()
        elif choice == "2":
            upload_video_interactive()
        elif choice == "3":
            try:
                yt = YouTubeAPI(use_oauth=True)
                channel = yt.get_channel_info()
                if channel:
                    print(f"\n📺 Canal: {channel['snippet']['title']}")
                    print(f"   Descrição: {channel['snippet']['description'][:100]}...")
                    stats = channel["statistics"]
                    print(f"   Inscritos: {stats.get('subscriberCount', 'N/A')}")
                    print(f"   Visualizações: {stats.get('viewCount', 'N/A')}")
                    print(f"   Vídeos: {stats.get('videoCount', 'N/A')}")
            except Exception as e:
                print(f"✗ Erro ao obter informações do canal: {e}")
        elif choice == "4":
            list_mp4_videos_interactive()
        elif choice == "0":
            print("Até logo!")
            break
        else:
            print("✗ Opção inválida")


if __name__ == "__main__":
    main()
