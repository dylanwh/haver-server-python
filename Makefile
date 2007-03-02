

haverdoc.txt: haverdoc.pl gendoc.pl
	perl haverdoc.pl | perl gendoc.pl > haverdoc.txt
