# -*- coding: utf-8 -*-
"""
STEP 4 – Train the Relational GCN.
"""

import torch
import torch.nn.functional as F
import pandas as pd
import numpy as np
import joblib
import time
from datetime import datetime
from sklearn.metrics import classification_report, roc_auc_score, average_precision_score, f1_score

from torch_geometric.nn import RGCNConv

from ..utils.config import DATA_DIR, MODEL_DIR, LOG_DIR, EPS, SEED
from ..utils.logger import get_logger

log = get_logger(__name__)

# ----------------------------------------------------------------------
# Model definition (same as the original script, but placed in a class)
# ----------------------------------------------------------------------


class FraudRGCN(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels, num_relations):
        super().__init__()
        self.conv1 = RGCNConv(in_channels, hidden_channels,
                              num_relations, aggr="mean")
        self.conv2 = RGCNConv(hidden_channels, out_channels,
                              num_relations, aggr="mean")
        self.classifier = torch.nn.Linear(out_channels, 2)  # two classes
        self.dropout = torch.nn.Dropout(p=0.3)

    def forward(self, x, edge_index, edge_type):
        x = F.relu(self.conv1(x, edge_index, edge_type))
        x = self.dropout(x)
        x = F.relu(self.conv2(x, edge_index, edge_type))
        logits = self.classifier(x)
        return logits

# ----------------------------------------------------------------------
# Helper – flatten the heterogeneous graph into a single edge_index / edge_type
# ----------------------------------------------------------------------


def flatten_hetero_graph(data):
    # The order we call the relations *must* match the order used when we create
    # the model (num_relations).  Keep it deterministic.
    relation_names = ["transacted_with", "shares_device", "shares_ip"]
    edge_index_list = []
    edge_type_list = []
    active = []

    for rel_id, rel_name in enumerate(relation_names):
        key = ("account", rel_name, "account")
        if key in data.edge_types:
            ei = data[key].edge_index
            edge_index_list.append(ei)
            edge_type_list.append(torch.full(
                (ei.shape[1],), rel_id, dtype=torch.long))
            active.append(rel_name)

    if not edge_index_list:
        raise RuntimeError("No edge types found in graph_data.pt")

    edge_index = torch.cat(edge_index_list, dim=1)
    edge_type = torch.cat(edge_type_list, dim=0)

    log.info(
        f"Flattened relations ({', '.join(active)}): {edge_index.shape[1]:,} edges")
    return data["account"].x, edge_index, edge_type, len(active)

# ----------------------------------------------------------------------
# Training loop
# ----------------------------------------------------------------------


def train_model(data, device):
    log.info("=" * 55)
    log.info("STEP 4: RGCN TRAINING")
    log.info("=" * 55)

    x, edge_index, edge_type, num_rel = flatten_hetero_graph(data)

    x = x.to(device)
    edge_index = edge_index.to(device)
    edge_type = edge_type.to(device)
    y = data["account"].y.to(device)

    train_mask = data["account"].train_mask.to(device)
    val_mask = data["account"].val_mask.to(device)

    log.info(f"Node features: {x.shape}")
    log.info(f"Edges: {edge_index.shape[1]:,} (relations: {num_rel})")
    log.info(
        f"Train nodes: {train_mask.sum().item():,} (fraud={y[train_mask].sum().item():,})")
    log.info(
        f"Val   nodes: {val_mask.sum().item():,} (fraud={y[val_mask].sum().item():,})")

    model = FraudRGCN(
        in_channels=x.shape[1],
        hidden_channels=64,
        out_channels=32,
        num_relations=num_rel,
    ).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    log.info(f"Model parameters: {total_params:,}")

    # class weighting (inverse frequency)
    n_fraud = y[train_mask].sum().item()
    n_benign = (train_mask.sum().item() - n_fraud)
    weight = torch.tensor([1.0, n_benign / (n_fraud + EPS)],
                          dtype=torch.float, device=device)
    log.info(f"Class weights – benign=1.0 | fraud={weight[1]:.2f}")

    criterion = torch.nn.CrossEntropyLoss(weight=weight)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=0.01, weight_decay=5e-4)
    scheduler = torch.optim.lr_scheduler.StepLR(
        optimizer, step_size=50, gamma=0.5)

    best_val_f1 = 0.0
    best_state = None
    patience = 30
    patience_cnt = 0
    loss_thresh = 1e-4
    loss_low_cnt = 0

    t0 = time.time()
    for epoch in range(1, 301):
        model.train()
        optimizer.zero_grad()
        logits = model(x, edge_index, edge_type)
        loss = criterion(logits[train_mask], y[train_mask])
        loss.backward()
        optimizer.step()
        scheduler.step()

        if epoch % 10 == 0:
            model.eval()
            with torch.no_grad():
                val_logits = model(x, edge_index, edge_type)
                val_probs = F.softmax(val_logits[val_mask], dim=1)[
                    :, 1].cpu().numpy()
                val_preds = val_logits[val_mask].argmax(1).cpu().numpy()
                y_val = y[val_mask].cpu().numpy()

                val_f1 = f1_score(y_val, val_preds, zero_division=0)
                val_aupr = average_precision_score(
                    y_val, val_probs) if len(np.unique(y_val)) > 1 else 0.0

                marker = " <-- best" if val_f1 > best_val_f1 else ""
                log.info(
                    f"Epoch {epoch:03d} | loss={loss.item():.4f} | "
                    f"val_F1={val_f1:.4f} | val_AUPRC={val_aupr:.4f} | lr={scheduler.get_last_lr()[0]:.5f}{marker}"
                )

                if val_f1 > best_val_f1:
                    best_val_f1 = val_f1
                    best_state = {k: v.clone()
                                  for k, v in model.state_dict().items()}
                    patience_cnt = 0
                else:
                    patience_cnt += 1
                    if patience_cnt >= patience:
                        log.info(
                            f"Early stopping (patience={patience}) at epoch {epoch}")
                        break

                # loss‑based early stop
                if loss.item() < loss_thresh:
                    loss_low_cnt += 1
                    if loss_low_cnt >= 5:
                        log.info(
                            f"Loss < {loss_thresh} for 5 checks → stop at epoch {epoch}")
                        break
                else:
                    loss_low_cnt = 0

    log.info(
        f"Training finished in {time.time() - t0:.2f}s – best val F1 {best_val_f1:.4f}")
    if best_state:
        model.load_state_dict(best_state)
    return model, x, edge_index, edge_type

# ----------------------------------------------------------------------
# Evaluation on the held‑out test set
# ----------------------------------------------------------------------


def evaluate(model, data, x, edge_index, edge_type):
    log.info("-" * 55)
    log.info("TEST SET EVALUATION (account‑level)")

    model.eval()
    with torch.no_grad():
        logits = model(x, edge_index, edge_type)
        probs = F.softmax(logits, dim=1)[:, 1].cpu().numpy()
        preds = (probs >= 0.5).astype(int)

    y_all = data["account"].y.numpy()
    test_mask = data["account"].test_mask.numpy()

    y_test = y_all[test_mask]
    p_test = probs[test_mask]
    d_test = preds[test_mask]

    log.info(
        f"Test distribution: {dict(zip(*np.unique(y_test, return_counts=True)))}")

    report = classification_report(y_test, d_test, labels=[0, 1],
                                   target_names=["Benign", "Fraud"], zero_division=0)
    for line in report.strip().split("\n"):
        log.info(f"  {line}")

    if len(np.unique(y_test)) > 1:
        auroc = roc_auc_score(y_test, p_test)
        auprc = average_precision_score(y_test, p_test)
        log.info(f"Test AUROC : {auroc:.4f}")
        log.info(f"Test AUPRC : {auprc:.4f}")
    else:
        log.warning("Only one class in test set – skipping AUROC/AUPRC")

    return probs


def run():
    t0 = time.time()
    data = torch.load(DATA_DIR / "graph_data.pt", weights_only=False)
    log.info(f"Loaded graph data: {data}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Using device: {device}")

    model, x, edge_index, edge_type = train_model(data, device)
    fraud_probs = evaluate(model, data, x, edge_index, edge_type)

    # Save model weights ---------------------------------------------------
    torch.save(model.state_dict(), MODEL_DIR / "rgcn_weights.pt")
    log.info(f"Saved model weights to {MODEL_DIR / 'rgcn_weights.pt'}")

    # Save config (so the inference wrapper can reconstruct the exact net) —
    num_relations = len([r for r in ["transacted_with", "shares_device", "shares_ip"]
                         if ("account", r, "account") in data.edge_types])
    cfg = {
        "in_channels": x.shape[1],
        "hidden_channels": 64,
        "out_channels": 32,
        "num_relations": num_relations,
    }
    joblib.dump(cfg, MODEL_DIR / "rgcn_config.pkl")
    log.info(f"Saved RGCN config to {MODEL_DIR / 'rgcn_config.pkl'}")

    # Write per‑account probabilities -----------------------------------------
    index_to_account = joblib.load(DATA_DIR / "index_to_account_map.pkl")
    results = pd.DataFrame({
        "account_id": [index_to_account[i] for i in range(len(fraud_probs))],
        "fraud_probability": fraud_probs,
    })
    results.to_csv(DATA_DIR / "rgcn_probabilities.csv", index=False)
    log.info(
        f"Saved per‑account prob to {DATA_DIR / 'rgcn_probabilities.csv'}")
    log.info(f"Step 4 total time: {time.time() - t0:.2f}s")


if __name__ == "__main__":
    run()
