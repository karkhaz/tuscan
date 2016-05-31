set boxwidth 0.8 relative
set style fill solid 1.0

set terminal eps
set output 'output/figures/{{ name }}.eps'

unset key

unset border
set xtics nomirror
set ytics nomirror
set border 3

set xlabel "LOC"
set ylabel "# Programs with LOC"
set title "Distribution of program sizes"

plot '-' using 2:xticlabels(1) with boxes lt -1
{{ data }}
EOF
