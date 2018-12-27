import torch
import os
import os.path as path
import argparse
import numpy as np
from model import CNN, VGG, LCNN, RawCNN
from torch.autograd import Variable
from torch import optim, nn
from torch.utils.data import DataLoader
from data_feeder import ASVDataSet, load_cnn_data
from torch.optim.lr_scheduler import ReduceLROnPlateau
from tqdm import tqdm


# parameters
print_str = "*"*20 + "{}" + "*"*20
asv_datapath=r"D:\experiments\anti\Data\ASVspoof2017_V2"
save_dir = "./result_try/rnn/"
train_protocol = path.join(asv_datapath, r"protocol_V2\ASVspoof2017_V2_train.trn.txt")
dev_protocol = path.join(asv_datapath, r"protocol_V2\ASVspoof2017_V2_dev.trl.txt")
final_protocol = [train_protocol, dev_protocol]


def get_args():
    parser = argparse.ArgumentParser(description="input the training compoents")

    parser.add_argument('--ft', '--feature_type', type=str, default='cqcc', help="the feature type")
    parser.add_argument('--mode', type=str, default='train', help='train or final')
    parser.add_argument('--sd', '--save_dir', type=str, default='./pkls/', help="the save dir")
    parser.add_argument('--tm', '--train_model', type=str, default='cnn', help="the training model")
    parser.add_argument('--bs', '--batch_size', type=int, default=128, help='bacth_size')
    parser.add_argument('--lr', '--learning_rate', type=float, default=2e-5, help='learning rate')
    parser.add_argument('--ne', '--num_epochs', type=int, default=20, help='num epoches')

    args = parser.parse_args()
    return args


def use_cuda():
    is_cuda = torch.cuda.is_available()
    return is_cuda


def save_checkpoint(state, save_path):
    torch.save(state, save_path)


def get_test_accuracy(data_loader, net, cross_entropy):
    total_loss = 0
    correct = 0
    total = 0
    net.eval()
    for tmp in tqdm(data_loader, desc="dev"):
        data = Variable(tmp['data'])
        label = Variable(tmp['label']).long().view(-1)
        if use_cuda():
            data, label = data.cuda(), label.cuda()
        predict = net(data)
        loss = cross_entropy(predict, label)
        total_loss += loss.item()
        _, predict_label = torch.max(predict.data, 1)
        correct += (predict_label.cpu() == label.cpu().data).sum()
        total += label.size(0)
    acc = float(correct) / total
    return acc, total_loss / total


def main():
    # do thing before training
    args = get_args()
    save_dir = os.path.join(args.sd, args.tm, args.ft)
    print(args)
    # input("*****Please check the params  also --> {} <--, Enter to continue*****".format(save_dir))
    os.makedirs(save_dir, exist_ok=True)
    mode = args.mode
    batch_size = args.bs
    feature_type = args.ft
    num_epochs = args.ne
    mean = 0.
    std = 1.
    # loading train data
    if mode == "train":
        train_data, train_label = load_cnn_data("train", train_protocol, mode=mode, feature_type=feature_type)
        # print(train_data.shape)
        # new_data = np.concatenate(train_data, axis=0)
        # print(new_data.shape)
        # mean = np.mean(new_data, axis=0)
        # print(mean.shape)
        # std = np.std(train_data, axis=0)
        # for i in range(0, train_data.shape[0]):
        #     mean = np.mean(train_data[i, :, :], axis=0)
        #     std = np.std(train_data[i, :, :], axis=0)
        #     train_data[i, :, :] = (train_data[i, :, :] - mean) / std
        # input()

        train_dataset = ASVDataSet(train_data, train_label, mode=mode)

        train_dataloader = DataLoader(train_dataset, batch_size=batch_size, num_workers=2, shuffle=True)

        dev_data, dev_label = load_cnn_data("dev", dev_protocol, mode=mode, feature_type=feature_type)
        # new_dev_data = np.concatenate(dev_data, 0)
        # mean, std = np.mean(new_dev_data, axis=0), np.std(new_dev_data, axis=0)
        # for i in range(0, dev_data.shape[0]):
        #     mean = np.mean(dev_data[i, :, :], axis=0)
        #     std = np.std(dev_data[i, :, :], axis=0)
        #     dev_data[i, :, :] = (dev_data[i, :, :] - mean) / std

        dev_dataset = ASVDataSet(dev_data, dev_label, mode=mode)
        dev_dataloader = DataLoader(dev_dataset, batch_size=batch_size, num_workers=2, shuffle=False)
    elif mode == "final":
        train_data, train_label = load_cnn_data(["train", "dev"], final_protocol,
                                            mode=mode, feature_type=feature_type)
        # mean = np.mean(train_data, axis=0)
        # std = np.std(train_data, axis=0)
        # train_data = (train_data - mean) / std
        train_dataset = ASVDataSet(train_data, train_label, mode="train")
        train_dataloader = DataLoader(train_dataset, batch_size=batch_size, num_workers=2, shuffle=True)

    if "lcnn" in args.tm:
        model = LCNN(num_classes=2)
    elif "rawcnn" in args.tm:
        model = RawCNN(50000, 0.2)
    elif "vgg" in args.tm:
        model = VGG(77, "VGG11")
    elif "cnn" in args.tm:
        model = CNN(77, 2, 0)

    if use_cuda():
        model = model.cuda()
    print(model)
    cross_entropy = nn.CrossEntropyLoss()
    optimizer = optim.ASGD(params=model.parameters(), lr=args.lr, weight_decay=5e-2)
    scheduler = ReduceLROnPlateau(optimizer, patience=0, min_lr=1e-7, factor=0.3, verbose=True)

    best_dev_accuracy = 0
    best_train_accuracy = 0
    for epoch in range(num_epochs):
        correct = 0
        total = 0
        train_loss = 0
        model.train()

        for tmp in tqdm(train_dataloader, desc="Epoch {}".format(epoch)):
            data = Variable(tmp['data'])
            label = Variable(tmp['label']).view(-1)
            if use_cuda():
                data, label = data.cuda(), label.cuda()

            optimizer.zero_grad()
            predict = model(data)

            _, predict_label = torch.max(predict.data, 1)
            correct += (predict_label.cpu() == label.cpu().data).sum()
            total += label.size(0)

            loss = cross_entropy(predict, label.long())
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        train_accuracy = float(correct) / total
        if mode == "final":
            if train_accuracy > best_train_accuracy:
                best_train_accuracy = train_accuracy
                save_checkpoint(
                    {'state_dict': model.cpu(), 'epoch': epoch, 'acc': train_accuracy, 'mean': mean, 'std': std},
                    save_path=os.path.join(save_dir, "best_eval.pkl")
                )
            save_checkpoint(
                {'state_dict': model.cpu(), 'epoch': epoch, 'acc': train_accuracy, 'mean': mean, 'std': std},
                save_path=os.path.join(save_dir, "final_eval_{}.pkl".format(epoch))
            )
            print("Epoch [%d/%d], Loss: %.4fe-4,  Train Acc %.2f%%" % (
                epoch+1, num_epochs, 1e4 * train_loss / total, train_accuracy * 100))
            print(print_str.format("Best Acc: {}".format(best_train_accuracy)))

            scheduler.step(train_loss/total)

            if use_cuda():
                model.cuda()

        if mode == "train":
            dev_accuracy, dev_loss = get_test_accuracy(dev_dataloader, model, cross_entropy)

            save_checkpoint(
                {'state_dict': model.cpu(), 'epoch': epoch, 'acc': dev_accuracy, 'mean': mean, 'std': std},
                save_path=os.path.join(save_dir, 'final_dev.pkl')
            )

            if dev_accuracy > best_dev_accuracy:
                best_dev_accuracy = dev_accuracy
                save_checkpoint(
                    {'state_dict': model.cpu(), 'epoch': epoch, 'acc': dev_accuracy, 'mean': mean, 'std': std},
                    save_path=os.path.join(save_dir, 'best_dev.pkl')
                )

            if use_cuda():
                model.cuda()

            print("Epoch [%d/%d], Train Loss: %.4fe-4, Train Acc %.2f%% Dev Loss: %.4fe-4 Dev Acc %.2f%% " % (
                epoch, num_epochs, 1e4 * train_loss / total, train_accuracy * 100,  dev_loss, dev_accuracy * 100
            ))
            print(print_str.format("Best Acc: {}".format(best_dev_accuracy)))
            scheduler.step(dev_loss)

if __name__ == '__main__':
    main()
