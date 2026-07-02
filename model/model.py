
import sys
import torch
import torch.nn as nn
import torch.nn.functional as F


## --- hyperparameters --- ##
block_size = 128     # 최대 문장 길이
n_embd = 256         # 임베딩 차원embedding dimension
n_head = 4           # 어텐션 헤드 attention heads
n_layer = 6          # transformer blocks
batch_size = 64
steps = 10000
lr = 1e-3
dropout = 0.2

torch.manual_seed(1337)


text = "\n".join(corpus.train.texts)
chars = sorted(list(set(text)))
vocab_size = len(chars)
print(f"vocab_size: {vocab_size}")
stoi = {c: i for i, c in enumerate(chars)}
itos = {i: c for c, i in stoi.items()}
encode = lambda s: [stoi[c] for c in s]
decode = lambda ids: "".join(itos[i] for i in ids)
data = torch.tensor(encode(text), dtype=torch.long)
n_train = int(0.9 * len(data))  # hold out the last 10% to measure overfitting
train_data, val_data = data[:n_train], data[n_train:]



device = (
    "cuda" if torch.cuda.is_available()
    else "mps" if torch.backends.mps.is_available()
    else "cpu"
)


def get_batch(split="train"):
    d = train_data if split == "train" else val_data
    ix = torch.randint(len(d) - block_size - 1, (batch_size,))
    x = torch.stack([d[i : i + block_size] for i in ix])
    y = torch.stack([d[i + 1 : i + block_size + 1] for i in ix])
    return x.to(device), y.to(device)


# 셀프 어텐션 역할을 하는 "CausalSelfAttention" 클래스
class CausalSelfAttention(nn.Module):
    """Multi-head scaled dot-product attention: softmax(QK^T / sqrt(d) + mask) V."""

    def __init__(self):
        super().__init__()
        self.qkv = nn.Linear(n_embd, 3 * n_embd)   # Q,K,V 한번에 계산하기 위한 레이어: 3분할을 위해서 출력크기 3 * n_embd설정
        self.proj = nn.Linear(n_embd, n_embd)      # 멀티헤드 어텐션 결과를 합친 후 최종 출력하는 레이어
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        B, T, C = x.shape            # B=배치크기, T=문장길이(시퀀스), C=임베딩차원 으로 분리
        head_dim = C // n_head       # 몫연산, head_dim=헤드당 차원

        # q, k, v 얻기 위해 텐서를 열방향으로  3등분
        ## self.qkv(x) = tensor[(B, T, 3*C)]
        ## 1차 변환: 텐서[B, T, C] -(차원 확장)-> 텐서[B, T, n_head, head_dim]
        q, k, v = self.qkv(x).chunk(3, dim=-1)


        ## 2차 변환: 텐서[B, T, n_head, head_dim] -(1,2 차원 교환)-> [B, n_head, T, head_dim]로 변환
        ### 텐서를 각 헤드별로 병렬계산하기위해서
        q = q.view(B, T, n_head, head_dim).transpose(1, 2)
        k = k.view(B, T, n_head, head_dim).transpose(1, 2)
        v = v.view(B, T, n_head, head_dim).transpose(1, 2)

        # 어텐션 점수: q와 k전치행렬 내적곱 진행후, 스케일링
        ## q[B, n_head, T, head_dim] @ k[B, n_head, head_dim, T] -> [B, n_head, T, T]
        ## head_dim**0.5 로 몫연산: 계산 값 오버플로우 방지
        att = q @ k.transpose(-2, -1) / head_dim**0.5

        # 좌측하단이 직각이며 True의 시작점인 삼각형(torch.tril) 마스크 생성
        ## 미래토큰을 볼수없고, 현재와 과거만 볼수있도록 강제함
        ### tensor([[True,  False, False, False],
        ###         [True,  True,  False, False],
        ###         [True,  True,  True,  False],
        ###         [True,  True,  True,  True ]])
        causal = torch.tril(torch.ones(T, T, dtype=torch.bool, device=x.device))

        # 위의 마스크를 반전시키고, True를 -inf로 변환
        ## softmax를 거치면 -inf는 0이되면서 미래토큰 완전 무시
        att = att.masked_fill(~causal, float("-inf"))
        att = self.drop(F.softmax(att, dim=-1))

        out = att @ v
        out = out.transpose(1, 2).reshape(B, T, C)
        return self.drop(self.proj(out))

# 트랜스포머의 디코더(셀프 어텐션 + 순전파) 역할을 하는 "Block"클래스
class Block(nn.Module):
    """Transformer decoder block: causal self-attention + feed-forward."""


    def __init__(self):
        super().__init__()
        self.ln1 = nn.LayerNorm(n_embd)            # 레이어 정규화1
        self.attn = CausalSelfAttention()          # 셀프 어센션
        self.ln2 = nn.LayerNorm(n_embd)            # 레이어 정규화2
        self.mlp = nn.Sequential(                  # 멀티 레이어 페셉트론
            nn.Linear(n_embd, 4 * n_embd),            ## 선형레이어1
            nn.GELU(),                                ## GELU(Gaussian Error Linear Unit)
            nn.Linear(4 * n_embd, n_embd),            ## 선형레이어2
            nn.Dropout(dropout),                      ## 드롭아웃
        )

    def forward(self, x):                         # Decoder
        x = x + self.attn(self.ln1(x))            ## input -> LN1 -> self-attention -> LN2 -> mlp ->output
        x = x + self.mlp(self.ln2(x))
        return x

class MiniGPT(nn.Module):
    def __init__(self):
        super().__init__()
        ## 토큰 임베딩
        self.tok_emb = nn.Embedding(vocab_size, n_embd)
        ## 포지셔널 임베딩(인코딩)
        self.pos_emb = nn.Embedding(block_size, n_embd)
        ## Decoder 반복
        self.blocks = nn.Sequential(*[Block() for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(n_embd)
        self.head = nn.Linear(n_embd, vocab_size)
    # idx = ? targets = ?
    def forward(self, idx, targets=None):
        T = idx.size(1)
        # 토큰 임베딩 + 포지셔널 임베딩(브로드캐스팅)
        x = self.tok_emb(idx) + self.pos_emb(torch.arange(T, device=idx.device)) #[B,T,n_embd] + [T,n_embd]
        # 최종 디코더 결과 레이어 정규화
        x = self.ln_f(self.blocks(x))
        # 위치별 단어확률 계산
        logits = self.head(x)
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, vocab_size), targets.view(-1))
        return logits, loss

    @torch.no_grad()
    def generate(self, idx, max_new_tokens):
        for _ in range(max_new_tokens):
            logits, _ = self(idx[:, -block_size:])
            probs = F.softmax(logits[:, -1, :], dim=-1)
            idx = torch.cat([idx, torch.multinomial(probs, 1)], dim=1)
        return idx


@torch.no_grad()
def estimate_loss(model):
    model.eval()
    out = {s: sum(model(*get_batch(s))[1].item() for _ in range(20)) / 20
           for s in ("train", "val")}
    model.train()
    return out


def train(model):
    print(f"{sum(p.numel() for p in model.parameters()):,} parameters, device={device}")
    opt = torch.optim.AdamW(model.parameters(), lr=lr)

    for step in range(steps):
        x, y = get_batch()
        _, loss = model(x, y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        if step % 1000 == 0 or step == steps - 1:
            est = estimate_loss(model)
            print(f"step {step:5d}  train {est['train']:.3f}  val {est['val']:.3f}", flush=True)

    torch.save(model.state_dict(), "mini_gpt.pt")
    print("saved weights to mini_gpt.pt")

    model.eval()
    prompt = torch.zeros((1, 1), dtype=torch.long, device=device)  # start token
    print("\n--- sample ---")
    print(decode(model.generate(prompt, 500)[0].tolist()))


def chat_prompt(model):
    model.load_state_dict(torch.load("mini_gpt.pt", map_location=device))
    model.eval()
    print("Type a prompt and the model will continue it (empty line or Ctrl-D to quit).")
    while True:
        try:
            prompt = input("> ")
        except EOFError:
            break
        if not prompt:
            break
        # drop characters the corpus (and thus the vocab) doesn't contain
        ids = [stoi[c] for c in prompt if c in stoi]
        if not ids:
            print("(no characters from the prompt are in the vocabulary)")
            continue
        idx = torch.tensor([ids], dtype=torch.long, device=device)
        out = model.generate(idx, 200)[0].tolist()
        print(decode(out[len(ids):]))  # print only the continuation

def chat_api(model, query):
    model.load_state_dict(torch.load("mini_gpt.pt", map_location=device))
    model.eval()
    try:
    ## 프롬프트 = 쿼리로 심플 설정
      prompt = query
    except EOFError:
      print(EOFError)
    if not prompt:
      print("prompt is empty")
        # drop characters the corpus (and thus the vocab) model = MiniGPT().to(device)doesn't contain
    ids = [stoi[c] for c in prompt if c in stoi]
    if not ids:
        print("(no characters from the prompt are in the vocabulary)")
    idx = torch.tensor([ids], dtype=torch.long, device=device)
    ## 스트림 기능 추가시 수정필요
    out = model.generate(idx, 200)[0].tolist()
    ##print(decode(out[len(ids):]))  # print only the continuation
    return decode(out[len(ids):])


model = MiniGPT().to(device)
chat_prompt(model)