
haverdoc.txt: haverdoc.yml
	perl gendoc.pl < haverdoc.yml > haverdoc.txt

haverdoc.yml: haverdoc.pl gendoc.pl
	twistd -ny haver.tac &  \
	perl haverdoc.pl > haverdoc.yml ; \
	kill `cat twistd.pid`
