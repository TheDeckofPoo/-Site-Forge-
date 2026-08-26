alias ps='ps -A -o user,pid,ppid,pcpu,stime,tty,time,comm'
alias vi='vim'
export EDITOR=vi
export P4CONFIG=~/.p4config
# Set terminal bell to a more reasonable value
# ESC[=ffff;ddB   ffff=frequency (Hz), dd=duration (ms)
printf "\033[=1760;60B" > /dev/con1
