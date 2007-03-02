

haverdoc.txt: haverdoc.pl gendoc.pl
	twistd -ny haver.tac &  \
	perl haverdoc.pl | perl gendoc.pl > haverdoc.txt; \
	kill `cat twistd.pid`
