// nvlink_saturate_forever.cu
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <csignal>
#include <vector>
#include <cuda_runtime.h>
#include <nccl.h>

#define CUDACHECK(cmd) do {                                   \
  cudaError_t e = cmd;                                        \
  if (e != cudaSuccess) {                                     \
    fprintf(stderr, "CUDA error %s:%d: %s\n",                 \
            __FILE__, __LINE__, cudaGetErrorString(e));       \
    std::exit(EXIT_FAILURE);                                  \
  }                                                           \
} while(0)

#define NCCLCHECK(cmd) do {                                   \
  ncclResult_t r = cmd;                                       \
  if (r != ncclSuccess) {                                     \
    fprintf(stderr, "NCCL error %s:%d: %s\n",                 \
            __FILE__, __LINE__, ncclGetErrorString(r));       \
    std::exit(EXIT_FAILURE);                                  \
  }                                                           \
} while(0)

static volatile sig_atomic_t keep_running = 1;

void handle_sigint(int) {
  keep_running = 0;
}

int main(int argc, char** argv) {
  const size_t bytes = (argc > 1) ? std::strtoull(argv[1], nullptr, 10)
                                  : (size_t)2 << 30; // default 2 GiB per GPU
  const int warmup = (argc > 2) ? std::atoi(argv[2]) : 20;
  const int report_every = (argc > 3) ? std::atoi(argv[3]) : 200;

  if (bytes % sizeof(float) != 0) {
    fprintf(stderr, "Buffer size must be a multiple of sizeof(float)\n");
    return EXIT_FAILURE;
  }

  std::signal(SIGINT, handle_sigint);
  std::signal(SIGTERM, handle_sigint);

  int ndev = 0;
  CUDACHECK(cudaGetDeviceCount(&ndev));
  if (ndev < 2) {
    fprintf(stderr, "Need at least 2 GPUs, found %d\n", ndev);
    return EXIT_FAILURE;
  }
  const int ngpus = ndev;

  std::vector<void*> sendbuf(ngpus), recvbuf(ngpus);
  std::vector<cudaStream_t> streams(ngpus);
  std::vector<ncclComm_t> comms(ngpus);

  ncclUniqueId id;
  NCCLCHECK(ncclGetUniqueId(&id));

  // Initialize 1 communicator per GPU.
  NCCLCHECK(ncclGroupStart());
  for (int i = 0; i < ngpus; ++i) {
    CUDACHECK(cudaSetDevice(i));
    CUDACHECK(cudaMalloc(&sendbuf[i], bytes));
    CUDACHECK(cudaMalloc(&recvbuf[i], bytes));
    CUDACHECK(cudaMemset(sendbuf[i], 1, bytes));
    CUDACHECK(cudaMemset(recvbuf[i], 0, bytes));
    CUDACHECK(cudaStreamCreate(&streams[i]));
    NCCLCHECK(ncclCommInitRank(&comms[i], ngpus, id, i));
  }
  NCCLCHECK(ncclGroupEnd());

  const size_t count = bytes / sizeof(float);

  // Warmup.
  for (int it = 0; it < warmup; ++it) {
    NCCLCHECK(ncclGroupStart());
    for (int i = 0; i < ngpus; ++i) {
      NCCLCHECK(ncclAllReduce(
          sendbuf[i], recvbuf[i], count,
          ncclFloat, ncclSum, comms[i], streams[i]));
    }
    NCCLCHECK(ncclGroupEnd());

    for (int i = 0; i < ngpus; ++i) {
      CUDACHECK(cudaSetDevice(i));
      CUDACHECK(cudaStreamSynchronize(streams[i]));
    }
  }

  printf("NCCL version      : %d.%d.%d\n",
         NCCL_MAJOR, NCCL_MINOR, NCCL_PATCH);
  printf("GPUs              : %d\n", ngpus);
  printf("Bytes per GPU     : %.2f MiB\n", bytes / 1024.0 / 1024.0);
  printf("Warmup iters      : %d\n", warmup);
  printf("Report every      : %d iterations\n", report_every);
  printf("Running until Ctrl+C ...\n");
  fflush(stdout);

  uint64_t total_iters = 0;

  while (keep_running) {
    cudaEvent_t start, stop;
    CUDACHECK(cudaSetDevice(0));
    CUDACHECK(cudaEventCreate(&start));
    CUDACHECK(cudaEventCreate(&stop));
    CUDACHECK(cudaEventRecord(start, streams[0]));

    int local_iters = 0;
    while (keep_running && local_iters < report_every) {
      NCCLCHECK(ncclGroupStart());
      for (int i = 0; i < ngpus; ++i) {
        NCCLCHECK(ncclAllReduce(
            sendbuf[i], recvbuf[i], count,
            ncclFloat, ncclSum, comms[i], streams[i]));
      }
      NCCLCHECK(ncclGroupEnd());

      ++local_iters;
      ++total_iters;
    }

    for (int i = 0; i < ngpus; ++i) {
      CUDACHECK(cudaSetDevice(i));
      CUDACHECK(cudaStreamSynchronize(streams[i]));
    }

    CUDACHECK(cudaSetDevice(0));
    CUDACHECK(cudaEventRecord(stop, streams[0]));
    CUDACHECK(cudaEventSynchronize(stop));

    float ms = 0.0f;
    CUDACHECK(cudaEventElapsedTime(&ms, start, stop));

    double sec = ms / 1e3;
    double totalGiB = (double)bytes * ngpus * local_iters
                    / (1024.0 * 1024.0 * 1024.0);
    double algGiBs = totalGiB / sec;

    printf("Total iters: %-12llu  Window iters: %-6d  Elapsed: %.3f s  Aggregate alg bw: %.2f GiB/s\n",
           (unsigned long long)total_iters, local_iters, sec, algGiBs);
    fflush(stdout);

    cudaEventDestroy(start);
    cudaEventDestroy(stop);
  }

  printf("\nStopping... draining outstanding work.\n");
  for (int i = 0; i < ngpus; ++i) {
    CUDACHECK(cudaSetDevice(i));
    CUDACHECK(cudaStreamSynchronize(streams[i]));
  }

  for (int i = 0; i < ngpus; ++i) {
    CUDACHECK(cudaSetDevice(i));
    cudaFree(sendbuf[i]);
    cudaFree(recvbuf[i]);
    cudaStreamDestroy(streams[i]);
    ncclCommDestroy(comms[i]);
  }

  printf("Done.\n");
  return 0;
}
