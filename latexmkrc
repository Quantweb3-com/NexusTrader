$pdflatex = 'xelatex -interaction=nonstopmode -shell-escape';
$pdf_mode = 1;
$preview_continuous_mode = 1;
$dvi_previewer = 'start xdvi -watchfile 1.5';
$ps_previewer  = 'start gv --watch';
$pdf_previewer = 'start evince';

# Clean up auxiliary files
$clean_ext = 'aux bbl blg idx ind lof lot out toc synctex.gz'; 
