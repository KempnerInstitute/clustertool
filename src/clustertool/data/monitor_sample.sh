gpu_lines=()
gpu_output=$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null)
IFS=','
while read -r gu mu mt; do
    gu=$(echo "$gu" | xargs); mu=$(echo "$mu" | xargs); mt=$(echo "$mt" | xargs)
    if [[ -n "$mt" && "$mt" != "0" ]]; then
        mem_util=$(awk "BEGIN {printf \"%.1f\", ($mu/$mt)*100}")
        gpu_lines+=("$gu $mem_util")
    else
        gpu_lines+=("N/A N/A")
    fi
done <<< "$gpu_output"
cpu=$(top -bn1 | grep "Cpu(s)" | awk '{print 100 - $8}' 2>/dev/null)
mem=$(free | awk '/Mem:/ {printf "%.1f", $3/$2*100}' 2>/dev/null)
# InfiniBand throughput from the port counters, not the IPoIB netdev: native RDMA
# traffic bypasses the netdev entirely, so ethtool sees almost none of a GPU job's
# network. port_{rcv,xmit}_data count 4-byte words, per the IB specification.
declare -a ib_ports=()
for state in /sys/class/infiniband/*/ports/*/state; do
  [ -e "$state" ] || continue
  port_dir=${state%/state}
  case "$(cat "$port_dir/link_layer" 2>/dev/null)" in InfiniBand) ;; *) continue ;; esac
  ib_ports+=("$port_dir")
done
declare -a rx1 tx1 ib_rates
for i in "${!ib_ports[@]}"; do
  rx1[$i]=$(cat "${ib_ports[$i]}/counters/port_rcv_data" 2>/dev/null)
  tx1[$i]=$(cat "${ib_ports[$i]}/counters/port_xmit_data" 2>/dev/null)
done
sleep 1
for i in "${!ib_ports[@]}"; do
  rx2=$(cat "${ib_ports[$i]}/counters/port_rcv_data" 2>/dev/null)
  tx2=$(cat "${ib_ports[$i]}/counters/port_xmit_data" 2>/dev/null)
  if [[ -n "${rx1[$i]:-}" && -n "${tx1[$i]:-}" && -n "$rx2" && -n "$tx2" ]]; then
    words=$(( (rx2 - rx1[$i]) + (tx2 - tx1[$i]) ))
    (( words < 0 )) && words=0
    ib_rates+=( "$(awk -v w="$words" 'BEGIN{printf "%.1f", w*4/1024/1024}')" )
  else
    ib_rates+=( "N/A" )
  fi
done
while (( ${#ib_rates[@]} < 4 )); do ib_rates+=( "N/A" ); done
for val in "${gpu_lines[@]}"; do echo -n "$val "; done
echo "${cpu:-N/A} ${mem:-N/A} ${ib_rates[0]} ${ib_rates[1]} ${ib_rates[2]} ${ib_rates[3]}"
