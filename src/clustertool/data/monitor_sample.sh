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
declare -a ib_ifaces=("ib0" "ib1" "ib2" "ib3")
declare -A rx1 tx1 rx2 tx2
declare -a ib_rates=()
for ib in "${ib_ifaces[@]}"; do
  if ip link show "$ib" &>/dev/null; then
    rx1[$ib]=$(ethtool -S "$ib" 2>/dev/null | awk '$1=="rx_bytes:" {print $2}')
    tx1[$ib]=$(ethtool -S "$ib" 2>/dev/null | awk '$1=="tx_bytes:" {print $2}')
  fi
done
sleep 1
for ib in "${ib_ifaces[@]}"; do
  if [[ -n "${rx1[$ib]:-}" && -n "${tx1[$ib]:-}" ]]; then
    rx2[$ib]=$(ethtool -S "$ib" 2>/dev/null | awk '$1=="rx_bytes:" {print $2}')
    tx2[$ib]=$(ethtool -S "$ib" 2>/dev/null | awk '$1=="tx_bytes:" {print $2}')
    if [[ -n "${rx2[$ib]}" && -n "${tx2[$ib]}" ]]; then
      delta=$(( (rx2[$ib] - rx1[$ib]) + (tx2[$ib] - tx1[$ib]) ))
      (( delta < 0 )) && delta=0
      ib_rates+=( "$(awk -v b="$delta" 'BEGIN{printf "%.1f", b/1024/1024}')" )
    else
      ib_rates+=( "N/A" )
    fi
  else
    ib_rates+=( "N/A" )
  fi
done
for val in "${gpu_lines[@]}"; do echo -n "$val "; done
echo "${cpu:-N/A} ${mem:-N/A} ${ib_rates[0]} ${ib_rates[1]} ${ib_rates[2]} ${ib_rates[3]}"
