# ------------------------------------------------------------------------------
# Code modified by Peter Naftaliev https://2d3d.ai too add functionality of sticks drawing between joints
#
# Copyright (c) 2018-present Microsoft
# Licensed under The Apache-2.0 License [see LICENSE for details]
# Written by Bin Xiao (Bin.Xiao@microsoft.com)
# ------------------------------------------------------------------------------


from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import csv
import os
import shutil

from PIL import Image
import torch
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim
import torch.utils.data
import torch.utils.data.distributed
import torchvision.transforms as transforms
import torchvision
import cv2
import numpy as np

import sys

# sys.path.append("../lib")
import time

import _init_paths
import math
import models
from config import cfg
from config import update_config
from core.inference import get_final_preds
from utils.transforms import get_affine_transform
import matplotlib.lines as mlines
import matplotlib.patches as mpatches


CTX = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
# CTX = torch.device('cpu')


class ColorStyle:
    def __init__(self, color, link_pairs, point_color):
        self.color = color
        self.link_pairs = link_pairs
        self.point_color = point_color

        for i in range(len(self.color)):
            self.link_pairs[i].append(tuple(np.array(self.color[i]) / 1.))

        self.ring_color = []
        for i in range(len(self.point_color)):
            self.ring_color.append(tuple(np.array(self.point_color[i]) / 1.))


# Xiaochu Style
# (R,G,B)
color1 = [(179, 0, 0), (228, 26, 28), (255, 255, 51),
          (49, 163, 84), (0, 109, 45), (255, 255, 51),
          (240, 2, 127), (240, 2, 127), (240, 2, 127), (240, 2, 127), (240, 2, 127),
          (217, 95, 14), (254, 153, 41), (255, 255, 51),
          (44, 127, 184), (0, 0, 255)]

link_pairs1 = [
    [15, 13], [13, 11], [11, 5],
    [12, 14], [14, 16], [12, 6],
    [3, 1], [1, 2], [1, 0], [0, 2], [2, 4],
    [9, 7], [7, 5], [5, 6],
    [6, 8], [8, 10],
]

point_color1 = [(240, 2, 127), (240, 2, 127), (240, 2, 127),
                (240, 2, 127), (240, 2, 127),
                (255, 255, 51), (255, 255, 51),
                (254, 153, 41), (44, 127, 184),
                (217, 95, 14), (0, 0, 255),
                (255, 255, 51), (255, 255, 51), (228, 26, 28),
                (49, 163, 84), (252, 176, 243), (0, 176, 240),
                (255, 255, 0), (169, 209, 142),
                (255, 255, 0), (169, 209, 142),
                (255, 255, 0), (169, 209, 142)]

xiaochu_style = ColorStyle(color1, link_pairs1, point_color1)

# Chunhua Style
# (R,G,B)
color2 = [(252, 176, 243), (252, 176, 243), (252, 176, 243),
          (0, 176, 240), (0, 176, 240), (0, 176, 240),
          (240, 2, 127), (240, 2, 127), (240, 2, 127), (240, 2, 127), (240, 2, 127),
          (255, 255, 0), (255, 255, 0), (169, 209, 142),
          (169, 209, 142), (169, 209, 142)]

link_pairs2 = [
    [15, 13], [13, 11], [11, 5],
    [12, 14], [14, 16], [12, 6],
    [3, 1], [1, 2], [1, 0], [0, 2], [2, 4],
    [9, 7], [7, 5], [5, 6], [6, 8], [8, 10],
]

point_color2 = [(240, 2, 127), (240, 2, 127), (240, 2, 127),
                (240, 2, 127), (240, 2, 127),
                (255, 255, 0), (169, 209, 142),
                (255, 255, 0), (169, 209, 142),
                (255, 255, 0), (169, 209, 142),
                (252, 176, 243), (0, 176, 240), (252, 176, 243),
                (0, 176, 240), (252, 176, 243), (0, 176, 240),
                (255, 255, 0), (169, 209, 142),
                (255, 255, 0), (169, 209, 142),
                (255, 255, 0), (169, 209, 142)]

chunhua_style = ColorStyle(color2, link_pairs2, point_color2)

COCO_KEYPOINT_INDEXES = {
    0: 'nose',
    1: 'left_eye',
    2: 'right_eye',
    3: 'left_ear',
    4: 'right_ear',
    5: 'left_shoulder',
    6: 'right_shoulder',
    7: 'left_elbow',
    8: 'right_elbow',
    9: 'left_wrist',
    10: 'right_wrist',
    11: 'left_hip',
    12: 'right_hip',
    13: 'left_knee',
    14: 'right_knee',
    15: 'left_ankle',
    16: 'right_ankle'
}

COCO_INSTANCE_CATEGORY_NAMES = [
    '__background__', 'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus',
    'train', 'truck', 'boat', 'traffic light', 'fire hydrant', 'N/A', 'stop sign',
    'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
    'elephant', 'bear', 'zebra', 'giraffe', 'N/A', 'backpack', 'umbrella', 'N/A', 'N/A',
    'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
    'bottle', 'N/A', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl',
    'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza',
    'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed', 'N/A', 'dining table',
    'N/A', 'N/A', 'toilet', 'N/A', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone',
    'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'N/A', 'book',
    'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]


def get_person_detection_boxes(model, img, threshold=0.5):
    with torch.no_grad():
        pil_image = Image.fromarray(img)  # Load the image
        transform = transforms.Compose([transforms.ToTensor()])  # Defing PyTorch Transform
        transformed_img = transform(pil_image)  # Apply the transform to the image
        pred = model([transformed_img.to(CTX)])  # Pass the image to the model
        # Use the first detected person
        pred_classes = [COCO_INSTANCE_CATEGORY_NAMES[i]
                        for i in list(pred[0]['labels'].cpu().numpy())]  # Get the Prediction Score
        pred_boxes = [[(i[0], i[1]), (i[2], i[3])]
                      for i in list(pred[0]['boxes'].cpu().detach().numpy())]  # Bounding boxes
        pred_scores = list(pred[0]['scores'].cpu().detach().numpy())

        person_boxes = []
        # Select box has score larger than threshold and is person
        for pred_class, pred_box, pred_score in zip(pred_classes, pred_boxes, pred_scores):
            if (pred_score > threshold) and (pred_class == 'person'):
                person_boxes.append(pred_box)

        return person_boxes


def get_pose_estimation_prediction(pose_model, image, centers, scales, transform):
    with torch.no_grad():
        rotation = 0

        # pose estimation transformation
        model_inputs = []
        for center, scale in zip(centers, scales):
            trans = get_affine_transform(center, scale, rotation, cfg.MODEL.IMAGE_SIZE)
            # Crop smaller image of people
            model_input = cv2.warpAffine(
                image,
                trans,
                (int(cfg.MODEL.IMAGE_SIZE[0]), int(cfg.MODEL.IMAGE_SIZE[1])),
                flags=cv2.INTER_LINEAR)

            # hwc -> 1chw
            model_input = transform(model_input)  # .unsqueeze(0)
            model_inputs.append(model_input)

        # n * 1chw -> nchw
        model_inputs = torch.stack(model_inputs)
        # print(model_input.shape)

        # compute output heatmap
        output = pose_model(model_inputs.to(CTX))
        coords, _ = get_final_preds(
            cfg,
            output.cpu().detach().numpy(),
            np.asarray(centers),
            np.asarray(scales))

        return coords


def box_to_center_scale(box, model_image_width, model_image_height):
    """convert a box to center,scale information required for pose transformation
    Parameters
    ----------
    box : list of tuple
        list of length 2 with two tuples of floats representing
        bottom left and top right corner of a box
    model_image_width : int
    model_image_height : int

    Returns
    -------
    (numpy array, numpy array)
        Two numpy arrays, coordinates for the center of the box and the scale of the box
    """
    center = np.zeros((2), dtype=np.float32)

    bottom_left_corner = box[0]
    top_right_corner = box[1]
    box_width = top_right_corner[0] - bottom_left_corner[0]
    box_height = top_right_corner[1] - bottom_left_corner[1]
    bottom_left_x = bottom_left_corner[0]
    bottom_left_y = bottom_left_corner[1]
    center[0] = bottom_left_x + box_width * 0.5
    center[1] = bottom_left_y + box_height * 0.5

    aspect_ratio = model_image_width * 1.0 / model_image_height
    pixel_std = 200

    if box_width > aspect_ratio * box_height:
        box_height = box_width * 1.0 / aspect_ratio
    elif box_width < aspect_ratio * box_height:
        box_width = box_height * aspect_ratio
    scale = np.array(
        [box_width * 1.0 / pixel_std, box_height * 1.0 / pixel_std],
        dtype=np.float32)
    if center[0] != -1:
        scale = scale * 1.25

    return center, scale


def prepare_output_dirs(prefix='/demo/'):
    pose_dir = os.path.join(prefix, "pose")
    if os.path.exists(pose_dir) and os.path.isdir(pose_dir):
        shutil.rmtree(pose_dir)
    os.makedirs(pose_dir, exist_ok=True)
    return pose_dir


def parse_args():
    parser = argparse.ArgumentParser(description='Train keypoints network')
    # general
    parser.add_argument('--cfg', type=str, required=True)
    parser.add_argument('--videoFile', type=str, required=False)
    parser.add_argument('--fileType', type=str, default='vid', required=True)
    parser.add_argument('--jsonDir', type=str)
    parser.add_argument('--imagesDirectory', type=str)
    parser.add_argument('--outputDir', type=str, default='demo/')
    parser.add_argument('--inferenceFps', type=int, default=20)
    parser.add_argument('--writeBoxFrames', action='store_true')
    parser.add_argument('--showImages', type=bool, default=False)

    parser.add_argument('opts',
                        help='Modify config options using the command-line',
                        default=None,
                        nargs=argparse.REMAINDER)

    args = parser.parse_args()

    # args expected by supporting codebase
    args.modelDir = ''
    args.logDir = ''
    args.dataDir = ''
    args.prevModelDir = ''
    return args

def video_inference(args, box_model, pose_model, pose_dir, pose_transform):
    # csv_output_rows = []
    # Loading an video
    vidcap = cv2.VideoCapture(args.videoFile)
    # vidcap = cv2.VideoCapture('demo_/john-wick.mp4')
    fps = vidcap.get(cv2.CAP_PROP_FPS)
    if fps < args.inferenceFps:
        print('desired inference fps is ' + str(args.inferenceFps) + ' but video fps is ' + str(fps))
        exit()
    skip_frame_cnt = round(fps / args.inferenceFps)
    frame_width = int(vidcap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(vidcap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    outcap = cv2.VideoWriter(
        '{}/{}_pose.avi'.format(args.outputDir, os.path.splitext(os.path.basename(args.videoFile))[0]),
        cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'), int(args.inferenceFps), (frame_width, frame_height))

    time_bbox = []
    time_pose = []
    time_total = []
    count = 0
    time_video_start = time.time()
    while vidcap.isOpened():
        total_now = time.time()
        ret, image_bgr = vidcap.read()
        count += 1

        if not ret:
            break

        if count % skip_frame_cnt != 0:
            continue
        print('Handling frame number ' + str(count))

        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

        # Clone 2 image for person detection and pose estimation
        if cfg.DATASET.COLOR_RGB:
            image_per = image_rgb.copy()
            image_pose = image_rgb.copy()
        else:
            image_per = image_bgr.copy()
            image_pose = image_bgr.copy()

        # Clone 1 image for debugging purpose
        image_debug = image_rgb.copy()

        # object detection box
        now = time.time()
        pred_boxes = get_person_detection_boxes(box_model, image_per, threshold=0.9)
        then = time.time()
        print("Find person bbox in: {} sec".format(then - now))
        time_bbox.append(then - now)

        # new_csv_row = []
        # Can not find people. Move to next frame
        if pred_boxes:

            if args.writeBoxFrames:
                for box in pred_boxes:
                    cv2.rectangle(image_debug, box[0], box[1], color=(0, 255, 0),
                                  thickness=3)  # Draw Rectangle with the coordinates

            # pose estimation : for multiple people
            centers = []
            scales = []
            for box in pred_boxes:
                center, scale = box_to_center_scale(box, cfg.MODEL.IMAGE_SIZE[0], cfg.MODEL.IMAGE_SIZE[1])
                centers.append(center)
                scales.append(scale)

            now = time.time()
            pose_preds = get_pose_estimation_prediction(pose_model, image_pose, centers, scales, transform=pose_transform)
            then = time.time()
            print("Find person pose in: {} sec".format(then - now))
            time_pose.append(then - now)


            coord_idx = 0
            for coords in pose_preds:
                ###################################
                # for k, link_pair in enumerate(xiaochu_style.link_pairs):
                # if link_pair[0] in joints_dict \
                #         and link_pair[1] in joints_dict:
                #     if dt_joints[link_pair[0], 2] < joint_thres \
                #             or dt_joints[link_pair[1], 2] < joint_thres \
                #             or vg[link_pair[0]] == 0 \
                #             or vg[link_pair[1]] == 0:
                #         continue
                # if k in range(6, 11):
                #     lw = 1
                # else:
                #     lw = ref / 100.

                # black ring
                # for k in range(dt_joints.shape[0]):
                #     if dt_joints[k, 2] < joint_thres \
                #             or vg[link_pair[0]] == 0 \
                #             or vg[link_pair[1]] == 0:
                #         continue
                #     if dt_joints[k, 0] > w or dt_joints[k, 1] > h:
                #         continue
                #     if k in range(5):
                #         radius = 1
                #     else:
                #         radius = ref / 100

                # circle = mpatches.Circle(tuple(dt_joints[k, :2]), radius=radius, ec='black', fc=ring_color[k], alpha=1, linewidth=1)
                # circle.set_zorder(1)

                # ax.add_patch(circle)
                ###################################
                # Draw each point on image
                dt_bb = pred_boxes[coord_idx]
                # dt_x0 = dt_bb[0] - dt_bb[2];
                # dt_x1 = dt_bb[0] + dt_bb[2] * 2
                # dt_y0 = dt_bb[1] - dt_bb[3];
                # dt_y1 = dt_bb[1] + dt_bb[3] * 2
                # dt_w = dt_x1 - dt_x0
                # dt_h = dt_y1 - dt_y0
                dt_w = dt_bb[1][0] - dt_bb[0][0]
                dt_h = dt_bb[1][1] - dt_bb[0][1]
                ref = min(dt_w, dt_h)

                join_idx = 0
                joints = {}
                for coord in coords:
                    x_coord, y_coord = int(coord[0]), int(coord[1])
                    joints[join_idx] = (x_coord, y_coord)
                    join_idx += 1

                for k, link_pair in enumerate(chunhua_style.link_pairs):
                    if k >= 6 and k < 11:
                        lw = 1  # TODO: maybe change line width if it doesn't look good
                    else:
                        lw = max(math.ceil(ref / 100), 1)
                    # line = mlines.Line2D(
                    #     np.array([joints[link_pair[0]][0],
                    #               joints[link_pair[1]][0]]),
                    #     np.array([joints[link_pair[0]][1],
                    #               joints[link_pair[1]][1]]),
                    #     ls='-', lw=lw, alpha=1, color=link_pair[2], )
                    # line.set_zorder(0)
                    # ax.add_line(line)
                    cv2.line(image_debug, joints[link_pair[0]], joints[link_pair[1]], link_pair[2], lw)
                for coord in coords:
                    x_coord, y_coord = int(coord[0]), int(coord[1])
                    if join_idx < 5:
                        radius = 1  # Might want to put some logic into radius size, according to person size. check the radius = ref / 100 in plot_coco
                    else:
                        radius = max(1, math.ceil(ref / 100))
                    cv2.circle(image_debug, (x_coord, y_coord), radius, (0, 0, 0),
                               2)  # TODO: might need to multiply color by 255, and might need to change thinkness 2 to 1
                    # cv2.circle(image_debug, (x_coord, y_coord), 4, (255, 0, 0), 2)
                    # new_csv_row.extend([x_coord, y_coord])

                coord_idx += 1

            total_then = time.time()

            text = "{:03.2f} sec".format(total_then - total_now)
            cv2.putText(image_debug, text, (100, 50), cv2.FONT_HERSHEY_SIMPLEX,
                        1, (0, 0, 255), 2, cv2.LINE_AA)
            time_total.append(total_then - total_now)

            if args.showImages:
                cv2.imshow("pos", image_debug)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        # csv_output_rows.append(new_csv_row)
        img_file = os.path.join(pose_dir, 'pose_{:08d}.jpg'.format(count))
        image_debug = cv2.cvtColor(image_debug, cv2.COLOR_RGB2BGR)
        cv2.imwrite(img_file, image_debug)
        outcap.write(image_debug)


    # write csv
    # csv_headers = ['frame']
    # for keypoint in COCO_KEYPOINT_INDEXES.values():
    #     csv_headers.extend([keypoint + '_x', keypoint + '_y'])
    #
    # csv_output_filename = os.path.join(args.outputDir, 'pose-data.csv')
    # with open(csv_output_filename, 'w', newline='') as csvfile:
    #     csvwriter = csv.writer(csvfile)
    #     csvwriter.writerow(csv_headers)
    #     csvwriter.writerows(csv_output_rows)

    vidcap.release()
    outcap.release()

    cv2.destroyAllWindows()
    time_video_end = time.time()
    print("Average time bbox {:03.2f} sec".format(sum(time_bbox) / len(time_bbox)))
    print("Average time pose {:03.2f} sec".format(sum(time_pose) / len(time_pose)))
    print("Average time total {:03.2f} sec".format(sum(time_total) / len(time_total)))
    print("Time video end-start {:03.2f} sec".format(time_video_end - time_video_start))

def image_inference(args, box_model, pose_model, pose_dir, pose_transform):
    time_bbox = []
    time_pose = []
    time_total = []
    count = 0
    time_experimentT_start = time.time()
    for root, dirs, files in os.walk(args.imagesDirectory):
        for name in files:
            file_dir = os.path.join(root, name)
            total_now = time.time()
            image_bgr = cv2.imread(file_dir)
            count += 1
            print('Handling image number ' + str(count))

            image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

            # Clone 2 image for person detection and pose estimation
            if cfg.DATASET.COLOR_RGB:
                image_per = image_rgb.copy()
                image_pose = image_rgb.copy()
            else:
                image_per = image_bgr.copy()
                image_pose = image_bgr.copy()

            # Clone 1 image for debugging purpose
            image_debug = image_rgb.copy()

            # object detection box
            now = time.time()
            pred_boxes = get_person_detection_boxes(box_model, image_per, threshold=0.9)
            then = time.time()
            print("Find person bbox in: {} sec".format(then - now))
            time_bbox.append(then - now)

            # new_csv_row = []
            # Can not find people. Move to next frame
            if pred_boxes:

                if args.writeBoxFrames:
                    for box in pred_boxes:
                        cv2.rectangle(image_debug, box[0], box[1], color=(0, 255, 0),
                                      thickness=3)  # Draw Rectangle with the coordinates

                # pose estimation : for multiple people
                centers = []
                scales = []
                for box in pred_boxes:
                    center, scale = box_to_center_scale(box, cfg.MODEL.IMAGE_SIZE[0], cfg.MODEL.IMAGE_SIZE[1])
                    centers.append(center)
                    scales.append(scale)

                now = time.time()
                pose_preds = get_pose_estimation_prediction(pose_model, image_pose, centers, scales,
                                                            transform=pose_transform)
                then = time.time()
                print("Find person pose in: {} sec".format(then - now))
                time_pose.append(then - now)

                coord_idx = 0
                for coords in pose_preds:
                    # Draw each point on image
                    dt_bb = pred_boxes[coord_idx]
                    dt_w = dt_bb[1][0] - dt_bb[0][0]
                    dt_h = dt_bb[1][1] - dt_bb[0][1]
                    ref = min(dt_w, dt_h)

                    join_idx = 0
                    joints = {}
                    for coord in coords:
                        x_coord, y_coord = int(coord[0]), int(coord[1])
                        joints[join_idx] = (x_coord, y_coord)
                        join_idx += 1

                    for k, link_pair in enumerate(chunhua_style.link_pairs):
                        if k >= 6 and k < 11:
                            lw = 1  # TODO: maybe change line width if it doesn't look good
                        else:
                            lw = max(math.ceil(ref / 100), 1)
                        cv2.line(image_debug, joints[link_pair[0]], joints[link_pair[1]], link_pair[2], lw)
                    for coord in coords:
                        x_coord, y_coord = int(coord[0]), int(coord[1])
                        if join_idx < 5:
                            radius = 1  # Might want to put some logic into radius size, according to person size. check the radius = ref / 100 in plot_coco
                        else:
                            radius = max(1, math.ceil(ref / 100))
                        cv2.circle(image_debug, (x_coord, y_coord), radius, (0, 0, 0),
                                   2)

                    coord_idx += 1

                total_then = time.time()

                text = "{:03.2f} sec".format(total_then - total_now)
                cv2.putText(image_debug, text, (100, 50), cv2.FONT_HERSHEY_SIMPLEX,
                            1, (0, 0, 255), 2, cv2.LINE_AA)
                time_total.append(total_then - total_now)

                if args.showImages:
                    cv2.imshow("pos", image_debug)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            img_file = os.path.join(pose_dir, '{}_pose.jpg'.format(name))
            image_debug = cv2.cvtColor(image_debug, cv2.COLOR_RGB2BGR)
            cv2.imwrite(img_file, image_debug)

def json_inference(args, json_data, pose_model, pose_dir, pose_transform):
    time_pose = []
    time_total = []
    count = 0

    time_experimentT_start = time.time()
    total_now = time.time()

    image_id = json_data['scene_graph']['image_id']
    image = json_data['image_contents']
    image_bgr = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image_input = image_bgr
    image_output = image

    # get person object bboxes
    person_class_id = 1
    person_objects = [e for e in json_data['scene_graph']['objects'] if e['class_id']==person_class_id]

    if len(person_objects)>0:
        # get bbox
        bbox_anns = [e['object_bbox'] for e in person_objects]
        bboxes = [[[e['x'],e['y']],[e['x']+e['width'],e['y']+e['height']]] for e in bbox_anns]

        centers = []
        scales = []
        for box in bboxes:
            center, scale = box_to_center_scale(box, cfg.MODEL.IMAGE_SIZE[0], cfg.MODEL.IMAGE_SIZE[1])
            centers.append(center)
            scales.append(scale)

        now = time.time()
        pose_preds = get_pose_estimation_prediction(pose_model, image_input, centers, scales,
                                                    transform=pose_transform)
        then = time.time()
        print("Find person pose in: {:.4f} sec".format(then - now))
        time_pose.append(then - now)

        for ii, coords in enumerate(pose_preds):
            # Draw each point on image
            dt_w = bbox_anns[ii]['width']
            dt_h = bbox_anns[ii]['height']
            ref = min(dt_w, dt_h)

            join_idx = 0
            joints = {}
            for coord in coords:
                x_coord, y_coord = int(coord[0]), int(coord[1])
                joints[join_idx] = (x_coord, y_coord)
                join_idx += 1

            for k, link_pair in enumerate(chunhua_style.link_pairs):
                if k >= 6 and k < 11:
                    lw = 1  # TODO: maybe change line width if it doesn't look good
                else:
                    lw = max(math.ceil(ref / 100), 1)
                cv2.line(image_output, joints[link_pair[0]], joints[link_pair[1]], link_pair[2], lw)
            for coord in coords:
                x_coord, y_coord = int(coord[0]), int(coord[1])
                if join_idx < 5:
                    radius = 1  # Might want to put some logic into radius size, according to person size. check the radius = ref / 100 in plot_coco
                else:
                    radius = max(1, math.ceil(ref / 100))
                cv2.circle(image_output, (x_coord, y_coord), radius, (0, 0, 0),2)

        total_then = time.time()
        time_total.append(total_then - total_now)

    img_file = os.path.join(pose_dir, '{}_pose.jpg'.format(image_id))
    cv2.imwrite(img_file, image_output)

def main():
    # transformation
    pose_transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])

    # cudnn related setting
    # cudnn.benchmark = cfg.CUDNN.BENCHMARK
    torch.backends.cudnn.deterministic = cfg.CUDNN.DETERMINISTIC
    torch.backends.cudnn.enabled = cfg.CUDNN.ENABLED

    args = parse_args()
    update_config(cfg, args)
    pose_dir = prepare_output_dirs(args.outputDir)
    # csv_output_rows = []

    json_data = None
    use_json = False
    if args.jsonDir != '' and os.path.exists(args.jsonDir):
        import json
        with open(args.jsonDir, 'r') as f:
            json_data = json.load(f)

        img_path = args.jsonDir.replace('.json','.jpg')
        json_data = {'image_contents': cv2.imread(img_path),
                     'scene_graph': json_data}
        use_json = True
    else:
        box_model = torchvision.models.detection.fasterrcnn_resnet50_fpn(pretrained=True)
        # box_model = torchvision.models.detection.fasterrcnn_mobilenet_v3_large_fpn(pretrained=True)
        box_model.to(CTX)
        box_model.eval()
    pose_model = eval('models.' + cfg.MODEL.NAME + '.get_pose_net')(
        cfg, is_train=False
    )
    # SHOW_IMAGES = args.showImages

    if cfg.TEST.MODEL_FILE:
        print('=> loading model from {}'.format(cfg.TEST.MODEL_FILE))
        pose_model.load_state_dict(torch.load(cfg.TEST.MODEL_FILE), strict=False)
    else:
        print('expected model defined in config at TEST.MODEL_FILE')

    pose_model.to(CTX)
    pose_model.eval()

    if use_json:
        """
        python tools/demo.py --cfg experiments/coco/hrnet/w32_384x288_adam_lr1e-3.yaml --fileType img --outputDir demo_out \
        --jsonDir keti_demo_input/2.json TEST.MODEL_FILE models/pytorch/pose_coco/pose_hrnet_w32_384x288.pth
        """
        json_inference(args, json_data, pose_model, pose_dir, pose_transform)
    else:
        if args.fileType == 'vid':
            video_inference(args, box_model, pose_model, pose_dir, pose_transform)
        else:
            image_inference(args, box_model, pose_model, pose_dir, pose_transform)



if __name__ == '__main__':
    main()
