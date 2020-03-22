# -*- coding: utf-8 -*-
"""chatbot_ecl.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/14YHXLj-ayzBHJ9T7yBlYUyiEracFeHDv
"""

from __future__ import unicode_literals, print_function, division
from io import open
import unicodedata
import string
import re
import random
import numpy as np

import torch
import torch.nn as nn
from torch.autograd import Variable
from torch import optim
import torch.nn.functional as F
import os

dirname=os.path.dirname(__file__)

DATA_FILE=os.path.join(dirname,('./data.txt'))
ENCODER_FILE= os.path.join(dirname,'./encoder20000_para.pkl')
DECODER_FILE= os.path.join(dirname,'./decoder20000_para.pkl')



"""# New Section"""

# Commented out IPython magic to ensure Python compatibility.
# %matplotlib inline

"""(1) Create Lang calss represente the dictionaire"""

SOS_token = 0
EOS_token = 1

class Lang:
    def __init__(self, name):
        self.name = name
        self.word2index = {"Null" :2}
        self.word2count = {}#count the frenquence of a word appear in the document
        self.index2word = {0: "SOS", 1: "EOS", 2:"Null"} # SOS : start of sentence; EOS: end of sentence; 
        # Null : word doesn't exist in the traning data.
        self.n_words = 3  # Count SOS and EOS and Null

    def addSentence(self, sentence):
        ''' add  a sentence to the class'''
        for word in sentence.split():
            if word == '':
                print('****************',sentence)
            self.addWord(word)
         
    def addWord(self, word):
        ''' add a word to the class '''
        if word not in self.word2index:
            self.word2index[word] = self.n_words
            self.word2count[word] = 1
            self.index2word[self.n_words] = word
            self.n_words += 1
        else:
            self.word2count[word] += 1

"""(2) Transform french to unicode and normalize the sentence"""

# Turn a Unicode string to plain ASCII, thanks to
# http://stackoverflow.com/a/518232/2809427
def unicodeToAscii(s):
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )

# Lowercase, trim, and remove non-letter characters except digits
def normalizeString(s):
    s = unicodeToAscii(s.lower().strip())
    s = re.sub(r"(['()/&!{}])", r" ", s)
    #s = re.sub(r"[^a-zA-Z.!?]+", r" ", s)
    #s = re.sub(r"[^a-zA-Z0-9?]+", r" ", s)
    #s = re.sub(r"[^a-zA-Z0-9?&\'\’\%\-]+", r" ", s)
    #s = re.sub(r"[^a-zA-Z0-9?&\%\-]+", r" ", s)
    return s

s="Il eût été bien de s'inscrire en 2017 !! N'est-ce pas ?"
# print(unicodeToAscii(s))
s = normalizeString(s)
# print(s)

import os
os.getcwd()

"""(3) Load data and create two dict : question and answer respectively"""

def readLangs(questions, answers, reverse=False,stem=False):
    # print("Reading lines...")
        
    lines = open(DATA_FILE, encoding='utf-8').\
        read().strip().split('\n')
    # Split every line into pairs and normalize
    pairs = [[normalizeString(s) for s in l.split('\t')] for l in lines]
    if stem:
        pairs = [[stemString(s) for s in l.split('\t')] for l in lines]

    # Reverse pairs, make Lang instances
    if reverse:
        pairs = [list(reversed(p)) for p in pairs]
        input_lang = Lang(answers)
        output_lang = Lang(questions)
    else:
        input_lang = Lang(questions)
        output_lang = Lang(answers)

    return input_lang, output_lang, pairs

"""# New Section"""

MAX_LENGTH = 25
# we use stopwords to delete those words not meaningfull
stopwords = 'de du des d le la les l ce c ci ça m me ma si t sur n en s si a y au un une on il nous vous je j a b c d e r f '.split()

#stopwords = []

def TrimWordsSentence(sentence):
    resultwords = [word for word in sentence.split() if word.lower() not in stopwords]
    resultwords = ' '.join(resultwords)
    return resultwords

def TrimWords(pairs):
    for pair in pairs: 
        pair[0] = TrimWordsSentence(pair[0])
        pair[1] = TrimWordsSentence(pair[1])
    return pairs

# delete longer sentences
def filterPair(p):
    return len(p[0].split()) < MAX_LENGTH and \
        len(p[1].split()) < MAX_LENGTH 

def filterPairs(pairs):
    return [pair for pair in pairs if filterPair(pair)]

def prepareData(lang1, lang2, reverse=False):
    input_lang, output_lang, pairs = readLangs(lang1, lang2, reverse)
    # print("Read %s sentence pairs" % len(pairs))
    pairs = TrimWords(pairs)
    
    for pair in [pair for pair in pairs if not filterPair(pair)]:
        print('%s (%d) -> %s (%d)' % (pair[0],len(pair[0].split()),pair[1],len(pair[1].split())))  
    
    pairs = filterPairs(pairs)
    
    # print('')
    # print("Trimmed to %s sentence pairs" % len(pairs))
    # print("Counting words...")
    for pair in pairs:
        input_lang.addSentence(pair[0])
        output_lang.addSentence(pair[1])
        if '' in output_lang.word2index: print(pair[1].split())
    # # print("Counted words:")
    # print(input_lang.name, input_lang.n_words)
    # print(output_lang.name, output_lang.n_words)
    return input_lang, output_lang, pairs

input_lang, output_lang, pairs = prepareData('questions', 'answers', False)

import os
os.getcwd()

class EncoderRNN(nn.Module):
    def __init__(self, input_size, hidden_size, n_layers=1):
        super(EncoderRNN, self).__init__()
        self.n_layers = n_layers
        self.hidden_size = hidden_size

        self.embedding = nn.Embedding(input_size, hidden_size)
        self.gru = nn.GRU(hidden_size, hidden_size)

    def forward(self, input, hidden):
        embedded = self.embedding(input).view(1, 1, -1)
        output = embedded
        for i in range(self.n_layers):
            output, hidden = self.gru(output, hidden)
        return output, hidden

    def initHidden(self):
        result = Variable(torch.zeros(1, 1, self.hidden_size))
        return result

class AttnDecoderRNN(nn.Module):
    def __init__(self, hidden_size, output_size, n_layers=1, dropout_p=0.1, max_length=MAX_LENGTH):
        super(AttnDecoderRNN, self).__init__()
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.n_layers = n_layers
        self.dropout_p = dropout_p
        self.max_length = max_length

        self.embedding = nn.Embedding(self.output_size, self.hidden_size)
        self.attn = nn.Linear(self.hidden_size * 2, self.max_length)
        self.attn_combine = nn.Linear(self.hidden_size * 2, self.hidden_size)
        self.dropout = nn.Dropout(self.dropout_p)
        self.gru = nn.GRU(self.hidden_size, self.hidden_size)
        self.out = nn.Linear(self.hidden_size, self.output_size)

    def forward(self, input, hidden, encoder_outputs):
        embedded = self.embedding(input).view(1, 1, -1)
        embedded = self.dropout(embedded)

        attn_weights = F.softmax(
            self.attn(torch.cat((embedded[0], hidden[0]), 1)))#, dim=1)
        attn_applied = torch.bmm(attn_weights.unsqueeze(0),
                                 encoder_outputs.unsqueeze(0))

        output = torch.cat((embedded[0], attn_applied[0]), 1)
        output = self.attn_combine(output).unsqueeze(0)

        for i in range(self.n_layers):
            output = F.relu(output)
            output, hidden = self.gru(output, hidden)

        output = F.log_softmax(self.out(output[0]))#, dim=1)
        return output, hidden, attn_weights

    def initHidden(self):
        result = Variable(torch.zeros(1, 1, self.hidden_size))
        return result



def indexesFromSentence(lang, sentence,MAX_LENGTH=25):
    words = sentence.split()
    if len(words)>MAX_LENGTH:
        new_words = random.choices(words,k=MAX_LENGTH)
    else:
        new_words = words
    
    
    a = []
    for word in new_words:
        try:
            a.append(lang.word2index[word])
        except KeyError:
            a.append(lang.word2index['Null'])
    
    return a

def variableFromSentence(lang, sentence):
    indexes = indexesFromSentence(lang, sentence)
    indexes.append(EOS_token)
    result = Variable(torch.LongTensor(indexes).view(-1, 1))
    return result

def variablesFromPair(pair):
    input_variable = variableFromSentence(input_lang, pair[0])
    target_variable = variableFromSentence(output_lang, pair[1])
    return (input_variable, target_variable)

teacher_forcing_ratio = 0.5

def train(input_variable, target_variable, encoder, decoder, encoder_optimizer, decoder_optimizer, criterion, max_length=MAX_LENGTH):
    encoder_hidden = encoder.initHidden()

    encoder_optimizer.zero_grad()
    decoder_optimizer.zero_grad()

    input_length = input_variable.size()[0]
    target_length = target_variable.size()[0]

    encoder_outputs = Variable(torch.zeros(max_length, encoder.hidden_size))

    loss = 0

    for ei in range(input_length):
        encoder_output, encoder_hidden = encoder(
            input_variable[ei], encoder_hidden)
        encoder_outputs[ei] = encoder_output[0][0]

    decoder_input = Variable(torch.LongTensor([[SOS_token]]))

    decoder_hidden = encoder_hidden

    use_teacher_forcing = True if random.random() < teacher_forcing_ratio else False

    if use_teacher_forcing:
        # Teacher forcing: Feed the target as the next input
        for di in range(target_length):
            
            decoder_output, decoder_hidden, decoder_attention = decoder(
                decoder_input, decoder_hidden, encoder_outputs)
            
            #decoder_output, decoder_hidden = decoder(
             #   decoder_input, decoder_hidden)
            
            loss += criterion(decoder_output, target_variable[di])
            decoder_input = target_variable[di]  # Teacher forcing

    else:
        # Without teacher forcing: use its own predictions as the next input
        for di in range(target_length):
            
            decoder_output, decoder_hidden, decoder_attention = decoder(
                decoder_input, decoder_hidden, encoder_outputs)
            
            #decoder_output, decoder_hidden = decoder(
             #   decoder_input, decoder_hidden)       
            
            topv, topi = decoder_output.data.topk(1)
            ni = topi[0][0].item()

            decoder_input = Variable(torch.LongTensor([[ni]]))
            decoder_input = decoder_input

            loss += criterion(decoder_output, target_variable[di])
            if ni == EOS_token:
                break

    loss.backward()

    encoder_optimizer.step()
    decoder_optimizer.step()

    #return loss.data[0] / target_length
    return loss.item() / target_length



import time
import math

def asMinutes(s):
    m = math.floor(s / 60)
    s -= m * 60
    return '%dm %ds' % (m, s)

def timeSince(since, percent):
    now = time.time()
    s = now - since
    es = s / (percent)
    rs = es - s
    return '%s (- %s)' % (asMinutes(s), asMinutes(rs))

def trainIters(encoder, decoder, n_iters, print_every=1000, plot_every=100, learning_rate=0.01,criterion = nn.NLLLoss()):
    start = time.time()
    plot_losses = []
    print_loss_total = 0  # Reset every print_every
    plot_loss_total = 0  # Reset every plot_every

    encoder_optimizer = optim.SGD(encoder.parameters(), lr=learning_rate)
    decoder_optimizer = optim.SGD(decoder.parameters(), lr=learning_rate)
    
    training_pairs = [variablesFromPair(random.choice(pairs))
                      for i in range(n_iters)]
   # criterion = nn.NLLLoss()
    #criterion = nn.CrossEntropyLoss()
    for iter in range(1, n_iters + 1):
        training_pair = training_pairs[iter - 1]
        input_variable = training_pair[0]
        target_variable = training_pair[1]

        loss = train(input_variable, target_variable, encoder,
                     decoder, encoder_optimizer, decoder_optimizer, criterion)
        print_loss_total += loss
        plot_loss_total += loss

        if iter % print_every == 0:
            print_loss_avg = print_loss_total / print_every
            print_loss_total = 0
            print('%s (%d %d%%) %.4f' % (timeSince(start, iter / n_iters),
                                         iter, iter / n_iters * 100, print_loss_avg))

        if iter % plot_every == 0:
            plot_loss_avg = plot_loss_total / plot_every
            plot_losses.append(plot_loss_avg)
            plot_loss_total = 0
        if iter % 2000 ==0:
            torch.save(encoder.state_dict(),'encoder_2_{}_para.pkl'.format(iter))
            torch.save(decoder.state_dict(),'decoder_2_{}_para.pkl'.format(iter))

    showPlot(plot_losses)

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


def showPlot(points):
    plt.figure()
    fig, ax = plt.subplots()
    # this locator puts ticks at regular intervals
    loc = ticker.MultipleLocator(base=0.2)
    ax.yaxis.set_major_locator(loc)
    plt.plot(points)

hidden_size = 256
#hidden_size = 100
encoder1 = EncoderRNN(input_lang.n_words, hidden_size)

attn_decoder1 = AttnDecoderRNN(hidden_size, output_lang.n_words,1, dropout_p=0.1)
encoder1.load_state_dict(torch.load(ENCODER_FILE))
attn_decoder1.load_state_dict(torch.load(DECODER_FILE))

def evaluate(encoder, decoder, sentence, max_length=MAX_LENGTH):
    sentence = unicodeToAscii(sentence)
    sentence = normalizeString(sentence)
    sentence = TrimWordsSentence(sentence)
    input_variable = variableFromSentence(input_lang, sentence)
    input_length = input_variable.size()[0]
    encoder_hidden = encoder.initHidden()

    encoder_outputs = Variable(torch.zeros(max_length, encoder.hidden_size))
    encoder_outputs = encoder_outputs

    for ei in range(input_length):
        encoder_output, encoder_hidden = encoder(input_variable[ei],
                                                 encoder_hidden)
        encoder_outputs[ei] = encoder_outputs[ei] + encoder_output[0][0]

    decoder_input = Variable(torch.LongTensor([[SOS_token]]))  # SOS
    decoder_input = decoder_input

    decoder_hidden = encoder_hidden

    decoded_words = []
    decoder_attentions = torch.zeros(max_length, max_length)

    for di in range(max_length):
        
        #decoder_output, decoder_hidden = decoder(
         #   decoder_input, decoder_hidden)

        decoder_output, decoder_hidden, decoder_attention = decoder(
            decoder_input, decoder_hidden, encoder_outputs)
        decoder_attentions[di] = decoder_attention.data

        topv, topi = decoder_output.data.topk(1)
        ni = topi[0][0].item()

        if ni == EOS_token:
            decoded_words.append('<EOS>')
            break
        else:
            decoded_words.append(output_lang.index2word[ni])

        decoder_input = Variable(torch.LongTensor([[ni]]))

    return decoded_words, decoder_attentions[:di + 1]
    #return decoded_words

def evaluateRandomly(encoder, decoder, n=10):
    for i in range(n):
        pair = random.choice(pairs)
        print('>', pair[0])
        print('=', pair[1])
        
        output_words, attentions = evaluate(encoder, decoder, pair[0])
        #output_words = evaluate(encoder, decoder, pair[0])
     
        output_sentence = ' '.join(output_words)
        print('<', output_sentence)
        print('')

# evaluateRandomly(encoder1, attn_decoder1)

def chat(encoder,decoder,sentence):
    answer = ''
    for i in evaluate(encoder,decoder,sentence)[0] :
        if i == "<EOS>":
            break
        answer = answer + ' ' + i
    # print("question : {}\n".format(sentence))
    print(answer)

s1 = "iltezata y combienrtare de  du  tcsss1 ze zettzveryreytrey ?"
s2 = "il combien de cours y du mth tc1 ?"
s3 = "cours combien mth tc1 ?"
s4 = "combien cours mth tc1 ?"

# chat(encoder1,attn_decoder1,s1)
# chat(encoder1,attn_decoder1,s2)
# chat(encoder1,attn_decoder1,s3)
# chat(encoder1,attn_decoder1,s4)




# print("RESPONSES FROM NODE SERVER********************")



import sys

text_from_node_server=str(sys.argv[1])

chat(encoder1,attn_decoder1,text_from_node_server)

sys.stdout.flush()


