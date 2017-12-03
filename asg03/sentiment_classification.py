
from pyspark import SparkContext
from pyspark.sql import SQLContext, DataFrame
from pyspark.ml import Pipeline
from pyspark.ml.feature import IDF, Tokenizer, CountVectorizer, StopWordsRemover, StringIndexer
from pyspark.ml.classification import DecisionTreeClassifier, RandomForestClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator
import sys
from functools import reduce

# Function for combining multiple DataFrames row-wise
def unionAll(*dfs):
    return reduce(DataFrame.unionAll, dfs)

if __name__ == "__main__":
    # Create a SparkContext and an SQLContext
    sc = SparkContext(appName="Sentiment Classification")
    sqlContext = SQLContext(sc)

    # Load data
    # wholeTextFiles(path, [...]) reads a directory of text files from a filesystem
    # Each file is read as a single record and returned in a key-value pair
    # The key is the path and the value is the content of each file
    reviews = sc.wholeTextFiles('hdfs://quickstart.cloudera:8020/user/cloudera/'+sys.argv[1]+'/*/*')
    #reviews = sc.wholeTextFiles('hdfs://quickstart.cloudera:8020/user/cloudera/txt_sentoken/*/*')
    
    # Create tuples: (class label, review text) - we ignore the file path
    # 1.0 for positive reviews
    # 0.0 for negative reviews
    reviews_f = reviews.map(lambda row: (1.0 if 'pos' in row[0] else 0.0, row[1]))

    # Convert data into a Spark SQL DataFrame
    # The first column contains the class label
    # The second column contains the review text
    dataset = reviews_f.toDF(['class_label', 'review'])


    # ----- PART II: FEATURE ENGINEERING -----

    # Tokenize the review text column into a list of words
    tokenizer = Tokenizer(inputCol='review', outputCol='words')
    words_data = tokenizer.transform(dataset)

    # Randomly split data into a training set, a development set and a test set
    # train = 60% of the data, dev = 20% of the data, test = 20% of the data
    # The random seed should be set to 42
    (train, dev, test) = words_data.randomSplit([.6, .2, .2], seed = 42)

    # TODO: Count the number of instances in, respectively, train, dev and test
    # Print the counts to standard output
    # [FIX ME!] Write code below
    print(train.count()) #685
    print(dev.count()) #261
    print(test.count()) #235

    # TODO: Count the number of positive/negative instances in, respectively, train, dev and test
    # Print the class distribution for each to standard output
    # The class distribution should be specified as the % of positive examples
    # [FIX ME!] Write code below

    #negative
    train_neg=train.filter(train.class_label == 0)
    train_neg.count() #581
    test_neg=test.filter(test.class_label == 0)
    test_neg.count() #194
    dev_neg=dev.filter(dev.class_label == 0)
    dev_neg.count() #225
    
    #positive
    train_pos=train.filter(train.class_label == 1) 
    train_pos.count() #104
    test_pos=test.filter(test.class_label == 1)
    test_pos.count() #41
    dev_pos=dev.filter(dev.class_label == 1)
    dev_pos.count() #36
    
    #class distribuition
    #N_POS/TOTAL
    train_dist = (train_pos.count()/train.count())*100
    test_dist = (test_pos.count()/test.count())*100
    dev_dist = (dev_pos.count()/dev.count())*100
    
    print('train distribution: '+str(train_dist)+' %') #0.1518
    print('test distribution: '+str(test_dist)+' %') #0.1744
    print('dev distribution: '+str(dev_dist)+' %') #0.1379
    
    # TODO: Create a stopword list containing the 100 most frequent tokens in the training data
    # Hint: see below for how to convert a list of (word, frequency) tuples to a list of words
    # stopwords = [frequency_tuple[0] for frequency_tuple in list_top100_tokens]
    # [FIX ME!] Write code below

    
    words=train.select(train.words)
    #This is the right one
    words_count=words.rdd.flatMap(lambda a: [(w,1) for w in a.words]).reduceByKey(lambda a,b: a+b)
    words_count=sorted(words_count.collect(), key=lambda x: x[1], reverse=True)
    words_count=words_count[:100]
    words_count = [frequency_tuple[0] for frequency_tuple in words_count]
    
    # TODO: Replace the [] in the stopWords parameter with the name of your created list
    # [FIX ME!] Modify code below
    remover = StopWordsRemover(inputCol='words', outputCol='words_filtered', stopWords=words_count)

    # Remove stopwords from all three subsets
    train_filtered = remover.transform(train)
    dev_filtered = remover.transform(dev)
    test_filtered = remover.transform(test)

    # Transform data to a bag of words representation
    # Only include tokens that have a minimum document frequency of 2
    cv = CountVectorizer(inputCol='words_filtered', outputCol='BoW', minDF=2.0)
    cv_model = cv.fit(train_filtered)
    train_data = cv_model.transform(train_filtered)
    dev_data = cv_model.transform(dev_filtered)
    test_data = cv_model.transform(test_filtered)

    # TODO: Print the vocabulary size (to STDOUT) after filtering out stopwords and very rare tokens
    # Hint: Look at the parameters of CountVectorizer
    # [FIX ME!] Write code below
   
    #NOT WORKING!!

    <!-- voc=train_data.select(train_data.words_filtered)
    voc2=voc.rdd.flatMap(lambda a: [(w,1) for w in a.voc]).distinct().count()
        
    voc2=voc.flatMap(lambda a: [(w,1) for w in a.voc]).distinct().count()
    
    voc2=voc.map(lambda word: (word, 1)).reduceByKey(lambda a, b: a + b)
     -->
        
    # Create a TF-IDF representation of the data
    idf = IDF(inputCol='BoW', outputCol='TFIDF')
    idf_model = idf.fit(train_data)
    train_tfidf = idf_model.transform(train_data)
    dev_tfidf = idf_model.transform(dev_data)
    test_tfidf = idf_model.transform(test_data)
    
      # ----- PART III: MODEL SELECTION -----

    # Provide information about class labels: needed for model fitting
    # Only needs to be defined once for all models (but included in all pipelines)
    label_indexer = StringIndexer(inputCol = 'class_label', outputCol = 'label')

    # Create an evaluator for binary classification
    # Only needs to be created once, can be reused for all evaluation
    evaluator = BinaryClassificationEvaluator()

    # Train a decision tree with default parameters (including maxDepth=5)
    dt_classifier_default = DecisionTreeClassifier(labelCol = 'label', featuresCol = 'TFIDF', maxDepth=5)

    # Create an ML pipeline for the decision tree model
    dt_pipeline_default = Pipeline(stages=[label_indexer, dt_classifier_default])

    # Apply pipeline and train model
    dt_model_default = dt_pipeline_default.fit(train_tfidf)

    # Apply model on devlopment data
    dt_predictions_default_dev = dt_model_default.transform(dev_tfidf)

    # Evaluate model using the AUC metric
    auc_dt_default_dev = evaluator.evaluate(dt_predictions_default_dev, {evaluator.metricName: 'areaUnderROC'})
    # AUC: 0.4614814814814815
    # Print result to standard output
    print('Decision Tree, Default Parameters, Development Set, AUC: ' + str(auc_dt_default_dev))

    # TODO: Check for signs of overfitting (by evaluating the model on the training set)
    
    # If train performances are better than test performances it overfit
    
    # [FIX ME!] Write code below

    auc_dt_default_train = evaluator.evaluate(dt_model_default.transform(train_tfidf), {evaluator.metricName: 'areaUnderROC'})
    
    # AUC: 0.3521034688203363
    
    # 0.46 > 0.35 => it does not overfit
    
    # TODO: Tune the decision tree model by changing one of its hyperparameters
    # Build and evalute decision trees with the following maxDepth values: 3 and 4.
    # [FIX ME!] Write code below

    dt_classifier_3 = DecisionTreeClassifier(labelCol = 'label', featuresCol = 'TFIDF', maxDepth=3)
    dt_classifier_4 = DecisionTreeClassifier(labelCol = 'label', featuresCol = 'TFIDF', maxDepth=4)
    
    #evaluating dt_classifier_3
    dt_pipeline_3 = Pipeline(stages=[label_indexer, dt_classifier_3])
    dt_model_3 = dt_pipeline_3.fit(train_tfidf)
    dt_predictions_3_dev = dt_model_3.transform(dev_tfidf)
    auc_dt_3_dev = evaluator.evaluate(dt_predictions_3_dev, {evaluator.metricName: 'areaUnderROC'})
    print('Decision Tree, Param = 3, Development Set, AUC: ' + str(auc_dt_3_dev))
    # AUC: 0.4707407407407407
    
    #evaluating dt_classifier_4
    dt_pipeline_4 = Pipeline(stages=[label_indexer, dt_classifier_4])
    dt_model_4 = dt_pipeline_4.fit(train_tfidf)
    dt_predictions_4_dev = dt_model_4.transform(dev_tfidf)
    auc_dt_4_dev = evaluator.evaluate(dt_predictions_4_dev, {evaluator.metricName: 'areaUnderROC'})
    print('Decision Tree, Param = 4, Development Set, AUC: ' + str(auc_dt_4_dev))
    # AUC: 0.4629012345679013
    
    # Decision tree with MaxDepth = 3 is better than 4.
    
    
    # Train a random forest with default parameters (including numTrees=20)
    rf_classifier_default = RandomForestClassifier(labelCol = 'label', featuresCol = 'TFIDF', numTrees=20)

    # Create an ML pipeline for the random forest model
    rf_pipeline_default = Pipeline(stages=[label_indexer, rf_classifier_default])

    # Apply pipeline and train model
    rf_model_default = rf_pipeline_default.fit(train_tfidf)

    # Apply model on development data
    rf_predictions_default_dev = rf_model_default.transform(dev_tfidf)

    # Evaluate model using the AUC metric
    auc_rf_default_dev = evaluator.evaluate(rf_predictions_default_dev, {evaluator.metricName: 'areaUnderROC'})

    # Print result to standard output
    print('Random Forest, Default Parameters, Development Set, AUC:' + str(auc_rf_default_dev))

    # AUC:0.6724691358024691
    
    # TODO: Check for signs of overfitting (by evaluating the model on the training set)
    # [FIX ME!] Write code below

    auc_rf_default_train = evaluator.evaluate(rf_model_default.transform(train_tfidf), {evaluator.metricName: 'areaUnderROC'})
    print('Random Forest, Default Parameters, Training Set, AUC:' + str(auc_rf_default_train))
    
    # AUC:0.9264365152919369
    # 0.92 >> 0.67. It clearly overfits.
    
    # TODO: Tune the random forest model by changing one of its hyperparameters
    # Build and evalute (on the dev set) another random forest with the following numTrees value: 100.
    # [FIX ME!] Write code below

    rf_classifier_100 = RandomForestClassifier(labelCol = 'label', featuresCol = 'TFIDF', numTrees=100)
    rf_pipeline_100 = Pipeline(stages=[label_indexer, rf_classifier_100])
    rf_model_100 = rf_pipeline_100.fit(train_tfidf)
    rf_predictions_100_dev = rf_model_100.transform(dev_tfidf)
    auc_rf_100_dev = evaluator.evaluate(rf_predictions_100_dev, {evaluator.metricName: 'areaUnderROC'})
    print('Random Forest, Default Parameters, Development Set, AUC:' + str(auc_rf_100_dev))
    
    # AUC:0.7117283950617285
    
    # ----- PART IV: MODEL EVALUATION -----

    # Create a new dataset combining the train and dev sets
    traindev_tfidf = unionAll(train_tfidf, dev_tfidf)

    # TODO: Evalute the best model on the test set
    # Build a new model from the concatenation of the train and dev sets in order to better utilize the data
    # [FIX ME!]
    
    rf_classifier_100 = RandomForestClassifier(labelCol = 'label', featuresCol = 'TFIDF', numTrees=100)
    rf_pipeline_100 = Pipeline(stages=[label_indexer, rf_classifier_100])
    rf_model_100 = rf_pipeline_100.fit(traindev_tfidf)
    rf_predictions_100_dev = rf_model_100.transform(test_tfidf)
    auc_rf_100_dev = evaluator.evaluate(rf_predictions_100_dev, {evaluator.metricName: 'areaUnderROC'})
    print('Random Forest, Default Parameters, Development Set, AUC:' + str(auc_rf_100_dev))
    
    # AUC:0.7483027407593664
    # Performance is a little bit better than before (AUC: 0.71) because we used more data for the training phase. 
    # In fact, the new dataset is the union between train and dev sets.