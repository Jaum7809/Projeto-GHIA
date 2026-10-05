import os
import platform
import subprocess
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, scrolledtext
import requests
import sounddevice as sd
from scipy.io.wavfile import write
import speech_recognition as sr
import pyttsx3
from thefuzz import process

# ==========================================
# CONFIGURAÇÕES GERAIS
# ==========================================
MODELO_OLLAMA = "llama3.2"  # Altere para "llama3", "mistral", etc., conforme o seu 'ollama list'
OLLAMA_URL = "http://localhost:11434/api/generate"
DURACAO_GRAVACAO_SEGUNDOS = 5
TAXA_AMOSTRAGEM = 16000

# ==========================================
# NAVEGAÇÃO E ATALHOS MULTIPLATAFORMA
# ==========================================
def abrir_caminho(caminho):
    """Abre pastas ou arquivos de forma compatível com Linux e Windows."""
    try:
        if platform.system() == "Windows":
            os.startfile(caminho)
        else:
            subprocess.Popen(["xdg-open", caminho])
    except Exception as e:
        print(f"[ERRO AO ABRIR]: {e}")

ATALHOS = {
    "abrir navegador": lambda: webbrowser.open("https://www.google.com"),
    "abrir google": lambda: webbrowser.open("https://www.google.com"),
    "abrir youtube": lambda: webbrowser.open("https://www.youtube.com"),
    "abrir portal faculdade": lambda: webbrowser.open("https://estudante.estacio.br"),
    "abrir downloads": lambda: abrir_caminho(os.path.expanduser("~/Downloads")),
    "abrir documentos": lambda: abrir_caminho(os.path.expanduser("~/Documents")),
    "abrir pasta pessoal": lambda: abrir_caminho(os.path.expanduser("~"))
}

# ==========================================
# MÓDULO DE VOZ (SÍNTESE & RECONHECIMENTO)
# ==========================================
def falar_texto(texto):
    """Executa a síntese de voz pyttsx3 em uma thread separada."""
    def _falar():
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 180)  # Velocidade da fala
            engine.say(texto)
            engine.runAndWait()
        except Exception as e:
            print(f"[ERRO SÍNTESE DE VOZ]: {e}")

    threading.Thread(target=_falar, daemon=True).start()

def gravar_e_transcrever(duracao=DURACAO_GRAVACAO_SEGUNDOS, taxa=TAXA_AMOSTRAGEM):
    """Grava áudio via SoundDevice e converte em texto com SpeechRecognition."""
    arquivo_temp = "temp_input.wav"
    try:
        # Gravação usando sounddevice
        gravacao = sd.rec(int(duracao * taxa), samplerate=taxa, channels=1, dtype='int16')
        sd.wait()
        write(arquivo_temp, taxa, gravacao)

        # Transcrição usando SpeechRecognition sobre o arquivo gerado
        recognizer = sr.Recognizer()
        with sr.AudioFile(arquivo_temp) as source:
            audio_data = recognizer.record(source)
            texto = recognizer.recognize_google(audio_data, language="pt-BR")
            return texto.strip()

    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"[ERRO ÁUDIO]: {e}")
        return ""
    finally:
        if os.path.exists(arquivo_temp):
            os.remove(arquivo_temp)

# ==========================================
# INTEGRAÇÃO OLLAMA
# ==========================================
def consultar_ollama(prompt):
    """Envia uma requisição para a API local do Ollama."""
    system_prompt = (
        "Você é uma assistente virtual prestativa, inteligente e direta. "
        "Responda em português do Brasil de forma clara e concisa."
    )
    payload = {
        "model": MODELO_OLLAMA,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=45)
        if response.status_code == 200:
            return response.json().get("response", "Sem resposta do modelo.")
        else:
            return f"Erro Ollama ({response.status_code}): {response.text}"
    except requests.exceptions.ConnectionError:
        return "Erro: O serviço Ollama não está rodando. Inicie-o com 'ollama serve'."
    except Exception as e:
        return f"Erro na comunicação com Ollama: {e}"

# ==========================================
# INTERFACE GRÁFICA (TKINTER)
# ==========================================
class AssistenteApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Assistente Pessoal - Ollama")
        self.root.geometry("650x550")
        self.root.configure(bg="#1e1e2e")

        self._criar_interface()

    def _criar_interface(self):
        # Área de histórico de conversa
        self.chat_area = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, bg="#181825", fg="#cdd6f4",
            font=("Segoe UI" if platform.system() == "Windows" else "Ubuntu", 10),
            state='disabled'
        )
        self.chat_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Barra de status
        self.lbl_status = tk.Label(
            self.root, text="Status: Pronto", bg="#1e1e2e", fg="#a6adc8", anchor="w"
        )
        self.lbl_status.pack(padx=10, fill=tk.X)

        # Frame inferior para entradas
        frame_input = tk.Frame(self.root, bg="#1e1e2e")
        frame_input.pack(padx=10, pady=10, fill=tk.X)

        self.entry_prompt = tk.Entry(
            frame_input, bg="#313244", fg="#cdd6f4", insertbackground="white",
            font=("Segoe UI" if platform.system() == "Windows" else "Ubuntu", 11)
        )
        self.entry_prompt.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.entry_prompt.bind("<Return>", lambda e: self.enviar_texto())

        self.btn_enviar = tk.Button(
            frame_input, text="Enviar", bg="#89b4fa", fg="#11111b",
            font=("Ubuntu", 9, "bold"), command=self.enviar_texto
        )
        self.btn_enviar.pack(side=tk.LEFT, padx=2)

        self.btn_voz = tk.Button(
            frame_input, text="🎙️ Ouvir", bg="#a6e3a1", fg="#11111b",
            font=("Ubuntu", 9, "bold"), command=self.iniciar_escuta_thread
        )
        self.btn_voz.pack(side=tk.LEFT, padx=2)

        self.adicionar_mensagem("Assistente", "Olá! Como posso ajudar você hoje?")

    def atualizar_status(self, texto):
        """Atualiza a barra de status de forma segura na thread principal."""
        self.root.after(0, lambda: self.lbl_status.config(text=f"Status: {texto}"))

    def adicionar_mensagem(self, autor, texto):
        """Adiciona uma mensagem na caixa de texto."""
        def _inserir():
            self.chat_area.config(state='normal')
            self.chat_area.insert(tk.END, f"\n[{autor}]: {texto}\n")
            self.chat_area.see(tk.END)
            self.chat_area.config(state='disabled')
        self.root.after(0, _inserir)

    def processar_comando(self, texto_usuario):
        if not texto_usuario.strip():
            return

        self.adicionar_mensagem("Você", texto_usuario)
        self.atualizar_status("Processando...")

        # 1. Verifica se é um atalho/comando local usando Fuzzy Matching
        melhor_correspondencia = process.extractOne(texto_usuario.lower(), ATALHOS.keys())
        if melhor_correspondencia and melhor_correspondencia[1] >= 80:
            comando_chave = melhor_correspondencia[0]
            self.adicionar_mensagem("Assistente", f"Executando atalho: '{comando_chave}'")
            falar_texto(f"Executando {comando_chave}")
            ATALHOS[comando_chave]()
            self.atualizar_status("Pronto")
            return

        # 2. Se não for atalho, envia para o Ollama
        resposta_ollama = consultar_ollama(texto_usuario)
        self.adicionar_mensagem("Assistente (LLM)", resposta_ollama)
        falar_texto(resposta_ollama)
        self.atualizar_status("Pronto")

    def enviar_texto(self):
        prompt = self.entry_prompt.get()
        if prompt.strip():
            self.entry_prompt.delete(0, tk.END)
            threading.Thread(target=self.processar_comando, args=(prompt,), daemon=True).start()

    def iniciar_escuta_thread(self):
        def _escutar():
            self.atualizar_status("🎙️ Ouvindo microfone (5s)...")
            texto_fala = gravar_e_transcrever()

            if texto_fala:
                self.processar_comando(texto_fala)
            else:
                self.adicionar_mensagem("Sistema", "Não entendi o que foi dito ou nada foi detectado.")
                self.atualizar_status("Pronto")

        threading.Thread(target=_escutar, daemon=True).start()

# ==========================================
# EXECUÇÃO PRINCIPAL
# ==========================================
if __name__ == "__main__":
    root = tk.Tk()
    app = AssistenteApp(root)
    root.mainloop()