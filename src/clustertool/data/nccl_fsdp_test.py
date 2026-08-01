import os
from functools import partial

import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributed import destroy_process_group, init_process_group
from torch.distributed.fsdp import FullyShardedDataParallel as FSDP
from torch.distributed.fsdp import ShardingStrategy
from torch.utils.data import DataLoader, DistributedSampler

rank = int(os.environ["SLURM_PROCID"])
world_size = int(os.environ["WORLD_SIZE"])
gpus_per_node = int(os.environ["SLURM_GPUS_ON_NODE"])
device = rank % gpus_per_node
torch.cuda.set_device(device)
init_process_group(backend="nccl", rank=rank, world_size=world_size)

layer_1_units, layer_2_units, layer_3_units = 6, 4, 2
model = nn.Sequential(
    nn.Linear(layer_1_units, layer_2_units), nn.Linear(layer_2_units, layer_3_units)
)


def auto_wrap_policy(module, recurse, nonwrapped_numel, min_num_params=10):
    return nonwrapped_numel >= min_num_params


model = FSDP(
    model,
    auto_wrap_policy=partial(auto_wrap_policy, min_num_params=10),
    sharding_strategy=ShardingStrategy.FULL_SHARD,
    device_id=device,
)

num_samples, batch_size = 1024, 32
dataset = list(
    zip(torch.randn(num_samples, layer_1_units), torch.randn(num_samples, layer_3_units))
)
sampler = DistributedSampler(dataset, num_replicas=world_size, rank=rank)
dataloader = DataLoader(dataset, batch_size=batch_size, sampler=sampler)

print(f"GPU{device} on Host {os.uname().nodename.split('.')[0]} : Rank {rank}")

optimizer = optim.SGD(model.parameters(), lr=0.01)
loss_fn = nn.MSELoss()
model.train()
for x, y in dataloader:
    x, y = x.to(device), y.to(device)
    loss = loss_fn(model(x), y)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

destroy_process_group()
