import torch.utils.data as D
import cv2
import numpy as np
#from torchvision import transforms
import marcalAugmentor
import datasetConfig
#import Augmentor
#from torchsample.transforms import RangeNormalize
#import torch

WORD_LEVEL = True
VGG_NORMAL = True
# train data: 46945
# valid data: 6445
# test data: 13752

RM_BACKGROUND = True
FLIP = False # flip the image
#BATCH_SIZE = 64
if WORD_LEVEL:
    OUTPUT_MAX_LEN = 23 # max-word length is 21  This value should be larger than 21+2 (<GO>+groundtruth+<END>)
    IMG_WIDTH = 1011 # m01-084-07-00 max_length
    baseDir = datasetConfig.baseDir_word
else:
    OUTPUT_MAX_LEN = 95 # line-level
    IMG_WIDTH = 2227 # m03-118-05.png max_length
    baseDir = datasetConfig.baseDir_line
IMG_HEIGHT = 64
#IMG_WIDTH = 256 # img_width < 256: padding   img_width > 256: resize to 256

#global_filename = []
#global_length = []
def labelDictionary():
    labels = [' ', '!', '"', '#', '&', "'", '(', ')', '*', '+', ',', '-', '.', '/',
              '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', ':', ';', '?',
              'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N',
              'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', '_',
              'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n',
              'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']
    letter2index = {label: n for n, label in enumerate(labels)}
    index2letter = {v: k for k, v in letter2index.items()}
    return len(labels), letter2index, index2letter

num_classes, letter2index, index2letter = labelDictionary()
tokens = {'GO_TOKEN': 0, 'END_TOKEN': 1, 'PAD_TOKEN': 2}
num_tokens = len(tokens.keys())


class IAM_words(D.Dataset):
    def __init__(self, file_label, augmentation=True):
        self.file_label = file_label
        self.output_max_len = OUTPUT_MAX_LEN
        self.augmentation = augmentation

    def __getitem__(self, index):
        word = self.file_label[index]
        file_name, thresh = word[0].split(',')
        if WORD_LEVEL:
            subdir = 'words/'
        else:
            subdir = 'lines/'
        url = baseDir + subdir + file_name + '.png'
        img, img_width = readImage_keepRatio(url, thresh=thresh, augmentation=self.augmentation)
        label, label_mask = self.label_padding(' '.join(word[1:]), num_tokens)
        return word[0], img, img_width, label
        #return {'index_sa': file_name, 'input_sa': in_data, 'output_sa': out_data, 'in_len_sa': in_len, 'out_len_sa': out_data_mask}

    def __len__(self):
        return len(self.file_label)

    def label_padding(self, labels, num_tokens):
        new_label_len = []
        ll = [letter2index[i] for i in labels]
        num = self.output_max_len - len(ll) - 2
        new_label_len.append(len(ll)+2)
        ll = np.array(ll) + num_tokens
        ll = list(ll)
        ll = [tokens['GO_TOKEN']] + ll + [tokens['END_TOKEN']]
        if not num == 0:
            ll.extend([tokens['PAD_TOKEN']] * num) # replace PAD_TOKEN

        def make_weights(seq_lens, output_max_len):
            new_out = []
            for i in seq_lens:
                ele = [1]*i + [0]*(output_max_len -i)
                new_out.append(ele)
            return new_out
        return ll, make_weights(new_label_len, self.output_max_len)


def readImage_keepRatio(file_path, thresh, augmentation=False,
                        target_img_width=IMG_WIDTH,
                        target_img_height=IMG_HEIGHT,
                        flip=FLIP, rm_background=RM_BACKGROUND,
                        vgg_normal=VGG_NORMAL):
    if rm_background:
        thresh = int(thresh)
    img = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), 0)  # cv2.IMREAD_GRAYSCALE

    if img is None:
        print('###!Cannot find image: ' + file_path)
    if rm_background:
        img[img > thresh] = 255
    # img = 255 - img
    # img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    # size = img.shape[0] * img.shape[1]

    rate = float(target_img_height) / img.shape[0]
    img = cv2.resize(img, (
        int(img.shape[1] * rate) + 1, target_img_height), interpolation=cv2.INTER_CUBIC)  # INTER_AREA con error
    # c04-066-01-08.png 4*3, for too small images do not augment
    if augmentation:  # augmentation for training data
        img_new = marcalAugmentor.augmentor(img)
        if img_new.shape[0] != 0 and img_new.shape[1] != 0:
            rate = float(target_img_height) / img_new.shape[0]
            img = cv2.resize(img_new, (
                int(img_new.shape[1] * rate) + 1, target_img_height),
                             interpolation=cv2.INTER_CUBIC)  # INTER_AREA con error
        else:
            img = 255 - img
    else:
        img = 255 - img

    img_width = img.shape[-1]

    if flip:  # because of using pack_padded_sequence, first flip, then pad it
        img = np.flip(img, 1)

    if img_width > target_img_width:
        outImg = cv2.resize(img, (target_img_width, target_img_height),
                            interpolation=cv2.INTER_AREA)
        # outImg = img[:, :IMG_WIDTH]
        img_width = target_img_width
    else:
        outImg = np.zeros((target_img_height, target_img_width), dtype='uint8')
        outImg[:, :img_width] = img
    outImg = outImg / 255.  # float64
    outImg = outImg.astype('float32')
    if vgg_normal:
        mean = [0.485, 0.456, 0.406]
        std = [0.229, 0.224, 0.225]
        outImgFinal = np.zeros([3, *outImg.shape], dtype='float32')
        for i in range(3):
            outImgFinal[i] = (outImg - mean[i]) / std[i]
        return outImgFinal, img_width

    outImg = np.vstack([np.expand_dims(outImg, 0)] * 3)  # GRAY->RGB
    return outImg, img_width


def loadData():
    if WORD_LEVEL:
        subname = 'word'
    else:
        subname = 'line'
    if RM_BACKGROUND:
        gt_tr = 'RWTH.iam_'+subname+'_gt_final.train.thresh'
        gt_va = 'RWTH.iam_'+subname+'_gt_final.valid.thresh'
        gt_te = 'RWTH.iam_'+subname+'_gt_final.test.thresh'
    else:
        pass
        #gt_tr = 'iam_word_gt_final.train'
        #gt_va = 'iam_word_gt_final.valid'
        #gt_te = 'iam_word_gt_final.test'

    with open(baseDir+gt_tr, 'r') as f_tr:
        data_tr = f_tr.readlines()
        file_label_tr = [i[:-1].split(' ') for i in data_tr]

    with open(baseDir+gt_va, 'r') as f_va:
        data_va = f_va.readlines()
        file_label_va = [i[:-1].split(' ') for i in data_va]

    with open(baseDir+gt_te, 'r') as f_te:
        data_te = f_te.readlines()
        file_label_te = [i[:-1].split(' ') for i in data_te]

    #total_num_tr = len(file_label_tr)
    #total_num_va = len(file_label_va)
    #total_num_te = len(file_label_te)
    #print('Loading training data ', total_num_tr)
    #print('Loading validation data ', total_num_va)
    #print('Loading testing data ', total_num_te)

    np.random.shuffle(file_label_tr)
    data_train = IAM_words(file_label_tr, augmentation=True)
    data_valid = IAM_words(file_label_va, augmentation=False)
    data_test = IAM_words(file_label_te, augmentation=False)
    return data_train, data_valid, data_test

if __name__ == '__main__':
    import time
    start = time.time()
    SHOW_IMG = False
    if WORD_LEVEL:
        imgName = 'p03-080-05-02'
        subdic = 'words/'
    else:
        imgName = 'p03-080-05'
        subdic = 'lines/'
    if SHOW_IMG:
        img = cv2.imread(baseDir+subdic+imgName+'.png', 0)
        data = IAM_words(None, augmentation=True)
        out_imgs = [data.readImage_keepRatio(imgName.split('.')[0]+',167', False)[0] for i in range(20)]

        rate = float(IMG_WIDTH) / out_imgs[0].shape[1]
        img = cv2.resize(img, (IMG_WIDTH, int(img.shape[0]*rate)), interpolation=cv2.INTER_AREA)
        outImg = img / 255
        final_img = np.vstack((outImg, *out_imgs))
        rate = 800 / final_img.shape[0]
        final_img2 = cv2.resize(final_img, (int(final_img.shape[1]*rate), 800), interpolation=cv2.INTER_AREA)
        cv2.imshow('Augmentor', final_img2)
        cv2.waitKey(0)

    else:
        data_train, data_valid, data_test = loadData()
        MAX_WIDTH = 500
        for i in range(len(data_train)):
            idx, img, width, label = data_train[i]
            if width > MAX_WIDTH:
                print('Width: ', width, 'Index:', idx)
        for i in range(len(data_valid)):
            idx, img, width, label = data_valid[i]
            if width > MAX_WIDTH:
                print('Width: ', width, 'Index:', idx)
        for i in range(len(data_test)):
            idx, img, width, label = data_test[i]
            if width > MAX_WIDTH:
                print('Width: ', width, 'Index:', idx)
